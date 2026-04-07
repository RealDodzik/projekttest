import os
import json
import datetime
import requests
import urllib3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
from pydub import AudioSegment

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UPLOAD_FOLDER = "/tmp/uploads"
DB_FILE = "/tmp/history.json"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
CORS(app)

AI_API_KEY = os.getenv("OPENAI_API_KEY", "nenastaveno")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")
AI_MODEL = os.getenv("AI_MODEL", "gemma3:27b")
MAX_UPLOAD_SIZE_MB = 20

# ---------------------------------------------------
# HTML TEMPLATE (BEZ ZMĚN)
# ---------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Filip Kuba - Audio AI Analyzer</title>
    <link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #fcf6f0;
            --card-bg: #ffffff;
            --text-main: #2d2d2d;
            --text-sub: #666;
            --accent-color: #e67e22;
            --accent-hover: #d35400;
            --border-color: #eee;
            --result-bg: #fff7e9;
            --transition: all 0.3s ease;
        }

        [data-theme="dark"] {
            --bg-color: #1a1a2e;
            --card-bg: #16213e;
            --text-main: #e9ecef;
            --text-sub: #a2a8d3;
            --accent-color: #7209b7;
            --accent-hover: #560bad;
            --border-color: #24344d;
            --result-bg: #0f172a;
        }

        body {
            background: var(--bg-color);
            font-family: 'Quicksand', sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            color: var(--text-main);
            transition: var(--transition);
        }

        .theme-toggle {
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--card-bg);
            border: 2px solid var(--accent-color);
            padding: 10px 15px;
            color: var(--accent-color);
            border-radius: 30px;
            font-weight: 700;
            cursor: pointer;
            transition: var(--transition);
        }

        .theme-toggle:hover {
            transform: scale(1.05);
        }

        .container {
            background: var(--card-bg);
            padding: 40px;
            border-radius: 20px;
            width: 90%;
            max-width: 650px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            transition: var(--transition);
            text-align: center;
        }

        h1 {
            color: var(--accent-color);
            font-weight: 700;
            margin-bottom: 10px;
        }

        .upload-box {
            border: 2px dashed var(--accent-color);
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 20px;
        }

        input[type="file"] {
            margin-bottom: 15px;
            width: 100%;
        }

        button {
            background: var(--accent-color);
            color: white;
            padding: 15px 25px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            width: 100%;
            font-size: 1.2em;
            font-weight: bold;
            transition: var(--transition);
        }

        button:hover {
            background: var(--accent-hover);
            transform: translateY(-2px);
        }

        #result {
            display: none;
            background: var(--result-bg);
            padding: 20px;
            border-radius: 12px;
            margin-top: 25px;
            text-align: left;
            border-left: 4px solid var(--accent-color);
        }
    </style>
</head>
<body data-theme="light">

<button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">🌙 Dark Mode</button>

<div class="container">
    <h1>Audio AI Analyzer</h1>
    <p class="author">By Filip Kuba</p>

    <div class="upload-box">
        <input type="file" id="file" accept=".wav,.mp3">
        <button onclick="upload()">Analyzovat soubor</button>
        <div id="loading" style="display:none; margin-top:10px; color: var(--accent-color); font-weight: 600;">AI přemýšlí...</div>
    </div>

    <div id="result">
        <p><strong>🎧 Média:</strong> <span id="media"></span></p>
        <p><strong>📝 Rozpoznaný text:</strong><br><span id="text"></span></p>
        <p><strong>🤖 AI Analýza:</strong><br><span id="ai"></span></p>
    </div>
</div>

<script>
function toggleTheme() {
    const body = document.body;
    const btn = document.getElementById("themeBtn");
    if (body.dataset.theme === "light") {
        body.dataset.theme = "dark";
        btn.textContent = "☀️ Light Mode";
    } else {
        body.dataset.theme = "light";
        btn.textContent = "🌙 Dark Mode";
    }
}

async function upload() {
    const file = document.getElementById("file").files[0];
    if (!file) return alert("Vyber soubor!");

    const form = new FormData();
    form.append("file", file);

    document.getElementById("loading").style.display = "block";
    document.getElementById("result").style.display = "none";

    try {
        let res = await fetch("/ai", { method: "POST", body: form });
        let data = await res.json();

        document.getElementById("media").textContent = data.media_type;
        document.getElementById("text").textContent = data.original_text;
        document.getElementById("ai").textContent = data.ai_analysis;
    } catch (e) {
        alert("Chyba při komunikaci s AI: " + e);
    }

    document.getElementById("loading").style.display = "none";
    document.getElementById("result").style.display = "block";
}
</script>

</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/status")
def status():
    return jsonify({"status": "online", "app": "Filip Kuba AI"})

def save_history(fname, ftype):
    entry = {"timestamp": str(datetime.datetime.now()), "filename": fname, "type": ftype}
    hist = []
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                hist = json.load(f)
        except:
            pass
    hist.append(entry)
    with open(DB_FILE, "w") as f:
        json.dump(hist, f, indent=4)

# ---------------------------------------------------
# NOVÝ FUNKČNÍ AUDIO → TEXT (Whisper API)
# ---------------------------------------------------
def transcribe_audio(path):
    try:
        with open(path, "rb") as audio_file:
            resp = requests.post(
                f"{AI_BASE_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                data={"model": "whisper-1"},
                files={"file": audio_file},
                verify=False
            )
        if resp.status_code != 200:
            return "Nerozpoznáno"
        return resp.json().get("text", "Nerozpoznáno")
    except Exception as e:
        print("Chyba STT:", e)
        return "Nerozpoznáno"

# ---------------------------------------------------
# AI ANALÝZA TEXTU
# ---------------------------------------------------
def ai_analysis(text):
    try:
        prompt = f"Shrň jednou větou tento text a napiš jestli je to řeč nebo píseň: {text}"
        resp = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            json={"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}]},
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            verify=False
        )
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Chyba při komunikaci s AI: {e}"

# ---------------------------------------------------
# HLAVNÍ API ENDPOINT
# ---------------------------------------------------
@app.route("/ai", methods=["POST"])
def analyze():
    if AI_API_KEY == "nenastaveno":
        return jsonify({"error": "API klíč není nastaven"}), 500

    f = request.files["file"]
    if not f:
        return jsonify({"error": "Soubor nebyl nahrán"}), 400

    fp = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(fp)

    save_history(f.filename, "Audio")

    # ---- AUDIO → TEXT ----
    text = transcribe_audio(fp)

    # ---- AI ANALÝZA ----
    if text == "Nerozpoznáno":
        ai_out = "Audio nebylo rozpoznáno, AI analýza není možná."
    else:
        ai_out = ai_analysis(text)

    return jsonify({
        "media_type": "Audio",
        "original_text": text,
        "ai_analysis": ai_out
    })

# ---------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
