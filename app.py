import os
import datetime
import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import speech_recognition as sr

# Získání absolutní cesty ke složce s tímto souborem
base_dir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
CORS(app)

# Nastavení proměnných pro AI
AI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://host.docker.internal:11434/v1")

UPLOAD_FOLDER = os.path.join(base_dir, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    # Posílá soubor index.html přímo z kořenové složky projektu
    return send_from_directory(base_dir, 'index.html')

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "autor": "Filip Kuba",
        "system": "Media Text Extractor",
        "aktualni_ai_url": AI_BASE_URL
    })

@app.route('/ai', methods=['POST'])
def process_media():
    if 'file' not in request.files:
        return jsonify({"chyba": "Chybi soubor"}), 400

    file = request.files['file']
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(file_path) as source:
            audio_data = recognizer.record(source)
            extrahovany_text = recognizer.recognize_google(audio_data, language="cs-CZ")
    except:
        extrahovany_text = "Nepodarilo se rozpoznat text."

    payload = {
        "model": "llama3.2:1b",
        "messages": [
            {"role": "system", "content": "Jsi asistent, ktery strucne shrnuje text."},
            {"role": "user", "content": f"Shrn tento text jednou kratkou vetou: {extrahovany_text}"}
        ],
        "temperature": 0.7
    }
    
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        full_url = f"{AI_BASE_URL.rstrip('/')}/chat/completions"
        response = requests.post(full_url, json=payload, headers=headers, timeout=30)
        ai_data = response.json()
        shrnuti = ai_data['choices'][0]['message']['content']
    except Exception as e:
        shrnuti = f"Chyba AI komunikace: {str(e)}"

    return jsonify({
        "original_text": extrahovany_text,
        "ai_shrnuti": shrnuti
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)