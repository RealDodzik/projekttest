import os
import json
import datetime
import requests
import urllib3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import speech_recognition as sr
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

HTML_TEMPLATE = """..."""  # Tvůj původní HTML obsah

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

def convert_to_wav16_mono(path):
    try:
        audio = AudioSegment.from_file(path)
        audio = audio.set_channels(1).set_frame_rate(16000)
        new_path = os.path.splitext(path)[0] + "_mono.wav"
        audio.export(new_path, format="wav")
        return new_path
    except Exception as e:
        print("Chyba při převodu:", e)
        return None

def process_audio(path):
    rec = sr.Recognizer()
    converted = convert_to_wav16_mono(path)
    if not converted:
        return "Audio nelze převést"
    try:
        with sr.AudioFile(converted) as src:
            audio = rec.record(src)
        return rec.recognize_sphinx(audio, language="cs-CZ")
    except:
        return "Nerozpoznáno"

@app.route("/ai", methods=["POST"])
def analyze():
    if AI_API_KEY == "nenastaveno":
        return jsonify({"error": "API klíč není nastaven"}), 500

    f = request.files["file"]
    if not f:
        return jsonify({"error": "Soubor nebyl nahrán"}), 400

    if f.content_length and f.content_length > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        return jsonify({"error": f"Soubor je větší než {MAX_UPLOAD_SIZE_MB} MB"}), 400

    fp = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(fp)

    media_type = "Audio"
    save_history(f.filename, media_type)

    text = process_audio(fp)
    if text in ["Nerozpoznáno", "Audio nelze převést"]:
        ai_output = "Audio nebylo rozpoznáno, AI analýza není možná."
    else:
        prompt = f"Shrň jednou větou tento text a napiš jestli je to řeč nebo píseň: {text}"
        try:
            res = requests.post(
                f"{AI_BASE_URL}/chat/completions",
                json={"model": AI_MODEL, "messages":[{"role":"user","content":prompt}], "stream":False},
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                verify=False,
                timeout=60
            )
            if res.headers.get("Content-Type", "").startswith("application/json"):
                ai_output = res.json()["choices"][0]["message"]["content"]
            else:
                ai_output = "AI server nevrátil JSON, analýza není možná."
        except Exception as e:
            ai_output = f"Chyba při komunikaci s AI: {e}"

    return jsonify({"media_type": media_type, "original_text": text, "ai_analysis": ai_output})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
