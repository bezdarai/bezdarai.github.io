import os, time, sqlite3
from flask import Flask, render_template, request, redirect, session, jsonify
from openai import OpenAI
import replicate
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_key")

# ===== API =====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")

# ===== RATE LIMIT =====
LIMIT = 15
WINDOW = 30
hits = defaultdict(list)

def limited(key):
    now = time.time()
    hits[key] = [t for t in hits[key] if now - t < WINDOW]
    if len(hits[key]) >= LIMIT:
        return True
    hits[key].append(now)
    return False

# ===== DB =====
def db():
    return sqlite3.connect("users.db")

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS chat(
        user TEXT,
        msg TEXT
    )""")
    c.commit()
    c.close()

# ===== AUTH =====
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u,p = request.form["username"], request.form["password"]
        c=db()
        user=c.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        c.close()
        if user and check_password_hash(user[2], p):
            session["user"]=u
            session["role"]=user[3]
            return redirect("/app")
        return "Неверно"
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    u,p=request.form["username"],generate_password_hash(request.form["password"])
    c=db()
    try:
        c.execute("INSERT INTO users VALUES(NULL,?,?,?)",(u,p,"user"))
        c.commit()
    except:
        return "Уже есть"
    c.close()
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ===== MAIN APP =====
@app.route("/app")
def main():
    if "user" not in session:
        return redirect("/")
    return render_template("index.html", user=session["user"])

# ===== ADMIN =====
@app.route("/admin")
def admin():
    if session.get("role")!="admin":
        return "403"
    c=db()
    users=c.execute("SELECT username,role FROM users").fetchall()
    c.close()
    return render_template("admin.html", users=users)

# ===== HEALTH =====
@app.route("/health")
def health():
    return jsonify({"status":"ok"})

# ===== CHAT =====
@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session: return jsonify({"error":"auth"}),401
    if limited(session["user"]): return jsonify({"error":"limit"}),429

    text=request.json.get("text","")
    r=client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":text}]
    )
    reply=r.choices[0].message.content

    c=db()
    c.execute("INSERT INTO chat VALUES(?,?)",(session["user"],text))
    c.commit(); c.close()

    return jsonify({"reply":reply})

# ===== IMAGE =====
@app.route("/image", methods=["POST"])
def image():
    if limited(session["user"]): return jsonify({"error":"limit"}),429
    p=request.json["text"]
    img=client.images.generate(model="gpt-image-1",prompt=p,size="512x512")
    return jsonify({"url":img.data[0].url})

# ===== VIDEO =====
@app.route("/video", methods=["POST"])
def video():
    if limited(session["user"]): return jsonify({"error":"limit"}),429
    out=replicate.run("anotherjesse/zeroscope-v2-xl",
        input={"prompt":request.json["text"],"num_frames":24,"fps":8})
    return jsonify({"video":out})

if __name__=="__main__":
    init_db()
    app.run()