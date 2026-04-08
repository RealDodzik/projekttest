import os
import requests
import urllib3
import speech_recognition as sr
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# Limit 1MB kvůli školnímu proxy serveru
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 

UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

AI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")
AI_MODEL = "gemma3:27b" # Jediný model, který máš povolený

# (Zde zůstává stejná HTML_TEMPLATE jako v minulém kroku)

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/ai", methods=["POST"])
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "Soubor nenalezen"}), 400
    
    f = request.files["file"]
    path = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(path)

    try:
        # 1. PŘEVOD AUDIO -> TEXT (Lokálně pomocí SpeechRecognition)
        # Nepoužíváme školní API, protože nemá oprávnění na Whisper
        recognizer = sr.Recognizer()
        with sr.AudioFile(path) as source:
            audio_data = recognizer.record(source)
            # Použijeme bezplatné Google rozpoznávání (nevyžaduje klíč)
            text = recognizer.recognize_google(audio_data, language="cs-CZ")

        # 2. ANALÝZA TEXTU (Pomocí školní Gemmy - toto je povoleno)
        chat_res = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            json={
                "model": AI_MODEL, 
                "messages": [{"role": "user", "content": f"Udělej krátký souhrn tohoto textu: {text}"}]
            },
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            verify=False,
            timeout=45
        )
        
        if chat_res.status_code != 200:
            return jsonify({"error": f"Chyba školní AI: {chat_res.text}"}), chat_res.status_code

        ai_text = chat_res.json()["choices"][0]["message"]["content"]

        return jsonify({
            "original_text": text,
            "ai_analysis": ai_text
        })

    except sr.UnknownValueError:
        return jsonify({"error": "AI nerozuměla nahrávce. Zkus mluvit zřetelněji."}), 400
    except Exception as e:
        return jsonify({"error": f"Chyba: {str(e)}"}), 500
    finally:
        if os.path.exists(path):
            os.remove(path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
