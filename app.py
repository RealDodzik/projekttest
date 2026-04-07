import os
import json
import datetime
import requests
import urllib3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import speech_recognition as sr

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
CORS(app)

AI_API_KEY = os.getenv("OPENAI_API_KEY", "nenastaveno")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")
AI_MODEL = os.getenv("AI_MODEL", "gemma3:27b")

DB_FILE = os.path.join(BASE_DIR, "history.json")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Audio AI Analyzér</title>
</head>
<body>
<h1>Audio → Text → AI shrnutí</h1>
<form method="post" action="/ai" enctype="multipart/form-data">
  <input type="file" name="file" accept=".wav,.mp3" required>
  <button type="submit">Analyzovat</button>
</form>
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
    entry = {
        "timestamp": str(datetime.datetime.now()),
        "filename": fname,
        "type": ftype
    }

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

def process_audio(path):
    rec = sr.Recognizer()
    with sr.AudioFile(path) as src:
        audio = rec.record(src)
    try:
        return rec.recognize_sphinx(audio, language="cs-CZ")
    except:
        return "Nerozpoznáno"

@app.route("/ai", methods=["POST"])
def analyze():
    if AI_API_KEY == "nenastaveno":
        return jsonify({"error": "API klíč není nastaven"}), 500

    f = request.files["file"]
    fp = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(fp)

    media_type = "Audio"
    save_history(f.filename, media_type)

    text = process_audio(fp)

    try:
        prompt = f"Shrň jednou větou tento text a napiš jestli je to řeč nebo píseň: {text}"
        res = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            json={
                "model": AI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            },
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            verify=False,
            timeout=60
        )
        ai_output = res.json()["choices"][0]["message"]["content"]
    except Exception as e:
        ai_output = "AI server nedostupný"

    return jsonify({
        "media_type": media_type,
        "original_text": text,
        "ai_analysis": ai_output
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
