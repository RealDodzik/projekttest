import os
import json
import datetime
import requests
import urllib3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

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

HTML_TEMPLATE = """ ... tu dej stejné HTML jako máš ... """

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

def transcribe_audio(path):
    """
    Používá OpenAI Whisper API pro převod audio -> text.
    """
    try:
        import httpx
        from openai import OpenAI

        client = OpenAI(
            api_key=AI_API_KEY,
            base_url=AI_BASE_URL,
            http_client=httpx.Client(verify=False)
        )

        with open(path, "rb") as audio_file:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return resp.text
    except Exception as e:
        print("Chyba při transkripci:", e)
        return None

@app.route("/ai", methods=["POST"])
def analyze():
    if AI_API_KEY == "nenastaveno":
        return jsonify({"error": "API klíč není nastaven"}), 500

    f = request.files.get("file")
    if not f:
        return jsonify({"error": "Soubor nebyl nahrán"}), 400

    if f.content_length and f.content_length > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        return jsonify({"error": f"Soubor je větší než {MAX_UPLOAD_SIZE_MB} MB"}), 400

    fp = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(fp)

    media_type = "Audio"
    save_history(f.filename, media_type)

    text = transcribe_audio(fp)
    if not text:
        return jsonify({
            "media_type": media_type,
            "original_text": "Nerozpoznáno",
            "ai_analysis": "Audio nebylo rozpoznáno, AI analýza není možná."
        })

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
