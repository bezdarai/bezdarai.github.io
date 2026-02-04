import os
from flask import Flask, render_template, request, redirect, session, jsonify
from openai import OpenAI
import replicate, sqlite3

app = Flask(__name__)
app.secret_key = "supersecretkey"

# 🔐 API ключи из переменных окружения (безопасно для интернета)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")

# ====== Функция для подключения к базе ==========
def get_db():
    return sqlite3.connect("users.db")

# ====== ЛОГИН ==========
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        session["user"] = request.form["username"]
        return redirect("/app")
    return render_template("login.html")

# ====== СТРАНИЦА ПРИЛОЖЕНИЯ ==========
@app.route("/app")
def app_page():
    if "user" not in session:
        return redirect("/")
    return render_template("index.html", user=session["user"])

# ====== ЧАТ ==========
@app.route("/chat", methods=["POST"])
def chat():
    text = request.json["text"]
    user = session["user"]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": text}]
    )

    reply = response.choices[0].message.content

    # Сохраняем историю
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS chat (user TEXT, msg TEXT)")
    db.execute("INSERT INTO chat VALUES (?, ?)", (user, text))
    db.commit()
    db.close()

    return jsonify({"reply": reply})

# ====== ИСТОРИЯ ЧАТА ==========
@app.route("/history")
def history():
    user = session["user"]
    db = get_db()
    rows = db.execute("SELECT msg FROM chat WHERE user=?", (user,)).fetchall()
    db.close()
    return jsonify([r[0] for r in rows])

# ====== ГЕНЕРАЦИЯ КАРТИНКИ ==========
@app.route("/image", methods=["POST"])
def image():
    img = client.images.generate(
        model="gpt-image-1",
        prompt=request.json["text"],
        size="512x512"
    )
    return jsonify({"url": img.data[0].url})

# ====== ГЕНЕРАЦИЯ ВИДЕО ==========
@app.route("/video", methods=["POST"])
def video():
    output = replicate.run(
        "anotherjesse/zeroscope-v2-xl",
        input={
            "prompt": request.json["text"],
            "num_frames": 24,
            "fps": 8
        }
    )
    return jsonify({"video": output})

# ====== ЗАПУСК ==========
if __name__ == "__main__":
    app.run(debug=True)