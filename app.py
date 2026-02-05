import os, time, sqlite3
from flask import Flask, render_template, request, redirect, session, jsonify
from openai import OpenAI
import replicate
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash

# ================== APP ==================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret")

# ================== API KEYS ==================
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_KEY = os.getenv("REPLICATE_API_TOKEN")

client = OpenAI(api_key=OPENAI_KEY)
os.environ["REPLICATE_API_TOKEN"] = REPLICATE_KEY

# ================== RATE LIMIT ==================
REQUEST_LIMIT = 10
TIME_WINDOW = 30
requests_log = defaultdict(list)

def rate_limited(key):
    now = time.time()
    requests_log[key] = [t for t in requests_log[key] if now - t < TIME_WINDOW]
    if len(requests_log[key]) >= REQUEST_LIMIT:
        return True
    requests_log[key].append(now)
    return False

# ================== DB ==================
def get_db():
    return sqlite3.connect("users.db")

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS chat (
            user TEXT,
            msg TEXT
        )
    """)
    db.commit()
    db.close()

# ================== LOG ==================
def log(msg):
    print(f"[SERVER] {msg}")

# ================== AUTH ==================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()
        db.close()

        if user and check_password_hash(user[2], password):
            session["user"] = username
            session["role"] = user[3]
            log(f"LOGIN: {username}")
            return redirect("/app")

        return "Неверный логин или пароль"

    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = generate_password_hash(request.form["password"])

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, password, "user")
        )
        db.commit()
    except:
        return "Пользователь уже существует"
    finally:
        db.close()

    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================== APP ==================
@app.route("/app")
def app_page():
    if "user" not in session:
        return redirect("/")
    return render_template("index.html", user=session["user"])

# ================== ADMIN ==================
@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return "Доступ запрещён", 403

    db = get_db()
    users = db.execute("SELECT username, role FROM users").fetchall()
    db.close()

    return render_template("admin.html", users=users)

# ================== HEALTH ==================
@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "openai": bool(OPENAI_KEY),
        "replicate": bool(REPLICATE_KEY)
    })

# ================== CHAT ==================
@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401

    key = session["user"]
    if rate_limited(key):
        return jsonify({"error": "Слишком много запросов"}), 429

    text = request.json.get("text", "").strip()
    if not text:
        return jsonify({"error": "Пусто"}), 400

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": text}]
    )

    reply = res.choices[0].message.content

    db = get_db()
    db.execute("INSERT INTO chat VALUES (?, ?)", (session["user"], text))
    db.commit()
    db.close()

    return jsonify({"reply": reply})

# ================== HISTORY ==================
@app.route("/history")
def history():
    if "user" not in session:
        return jsonify([])

    db = get_db()
    rows = db.execute(
        "SELECT msg FROM chat WHERE user=?",
        (session["user"],)
    ).fetchall()
    db.close()

    return jsonify([r[0] for r in rows])

# ================== IMAGE ==================
@app.route("/image", methods=["POST"])
def image():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401

    key = session["user"]
    if rate_limited(key):
        return jsonify({"error": "Лимит"}), 429

    prompt = request.json.get("text", "").strip()
    if not prompt:
        return jsonify({"error": "Пусто"}), 400

    img = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="512x512"
    )

    return jsonify({"url": img.data[0].url})

# ================== VIDEO ==================
@app.route("/video", methods=["POST"])
def video():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401

    key = session["user"]
    if rate_limited(key):
        return jsonify({"error": "Лимит"}), 429

    prompt = request.json.get("text", "").strip()
    if not prompt:
        return jsonify({"error": "Пусто"}), 400

    output = replicate.run(
        "anotherjesse/zeroscope-v2-xl",
        input={
            "prompt": prompt,
            "num_frames": 24,
            "fps": 8
        }
    )

    return jsonify({"video": output})

# ================== START ==================
if __name__ == "__main__":
    init_db()
    log("SERVER STARTED")
    app.run()