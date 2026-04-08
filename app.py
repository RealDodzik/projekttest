import os
import json
import datetime
import requests
import urllib3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
CORS(app)

# LIMIT 1MB - pokud uživatel nahraje víc, Flask mu rovnou vrátí chybu 413
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 

AI_API_KEY = os.getenv("OPENAI_API_KEY", "nenastaveno")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")
AI_MODEL = os.getenv("AI_MODEL", "gemma3:27b")

# ... (HTML_TEMPLATE zůstává stejná jako v minulé zprávě) ...
# POUŽIJ STEJNOU ŠABLONU JAKO PŘEDTÍM, JEN ZMĚNÍME PYTHON LOGIKU NÍŽE

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "Soubor je příliš velký! Školní server povoluje max 1 MB."}), 413

def transcribe_audio(path):
    try:
        with open(path, "rb") as audio_file:
            resp = requests.post(
                f"{AI_BASE_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                files={"file": audio_file},
                verify=False,
                timeout=30
            )
        
        if resp.status_code == 404:
            return "CHYBA: Školní server nepodporuje Whisper (převod zvuku na text). Zkus nahrát jen text (pokud to aplikace dovolí) nebo kontaktuj správce."
        
        if resp.status_code != 200:
            return f"Chyba API ({resp.status_code}): {resp.text}"
            
        return resp.json().get("text", "Nerozpoznáno")
    except Exception as e:
        return f"Chyba spojení: {str(e)}"

@app.route("/ai", methods=["POST"])
def analyze():
    try:
        if "file" not in request.files:
            return jsonify({"error": "Nebyl vybrán soubor"}), 400
            
        f = request.files["file"]
        fp = os.path.join(UPLOAD_FOLDER, f.filename)
        f.save(fp)

        # Volání STT
        text = transcribe_audio(fp)

        # Pokud STT nefunguje, nebudeme volat AI analýzu a rovnou vrátíme chybu
        if "CHYBA:" in text or "Chyba API" in text:
            return jsonify({
                "media_type": "Audio (Chyba)",
                "original_text": text,
                "ai_analysis": "Analýza neproběhla, protože nebylo možné získat text ze zvuku."
            })

        # Volání AI analýzy (chat)
        prompt = f"Shrň tento text: {text}"
        resp_ai = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            json={"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}]},
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            verify=False
        )
        
        ai_out = resp_ai.json()["choices"][0]["message"]["content"]

        return jsonify({
            "media_type": "Audio",
            "original_text": text,
            "ai_analysis": ai_out
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
