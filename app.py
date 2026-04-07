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
HTML_TEMPLATE = """REPLACE YOUR HTML HERE (NECHÁVÁM PŮVODNÍ, ABY CHAT NEBYL PŘÍLIŠ DLOUHÝ)"""

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
