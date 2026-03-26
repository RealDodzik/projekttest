import os
import datetime
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
import speech_recognition as sr

app = Flask(__name__)
# Povolení CORS pro komunikaci s prohlížečem
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/ping', methods=['GET'])
def ping():
    return "pong"

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "cas": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "autor": "Filip Kuba",
        "tema": "Media Text Extractor"
    })

@app.route('/ai', methods=['POST'])
def process_media():
    if 'file' not in request.files:
        return jsonify({"chyba": "Chybi soubor"}), 400

    file = request.files['file']
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    # --- EXTRAKCE TEXTU Z AUDIA ---
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(file_path) as source:
            audio_data = recognizer.record(source)
            # Převod řeči na text v češtině
            extrahovany_text = recognizer.recognize_google(audio_data, language="cs-CZ")
    except Exception as e:
        extrahovany_text = "Nepodarilo se rozpoznat text. Pouzijte prosim jasny .wav soubor."

    # --- VOLÁNÍ LOKÁLNÍ OLLAMY ---
    # host.docker.internal ukazuje z kontejneru na tvůj hostitelský Windows
    ollama_url = "http://host.docker.internal:11434/api/generate"
    payload = {
        "model": "llama3.2:1b",
        "prompt": f"Shrň tento text jednou krátkou větou: {extrahovany_text}",
        "stream": False
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=30)
        ai_data = response.json()
        return jsonify({
            "original_text": extrahovany_text,
            "ai_shrnuti": ai_data.get("response"),
            "status": "success"
        })
    except Exception as e:
        return jsonify({
            "original_text": extrahovany_text,
            "ai_shrnuti": "Ollama neodpovida (zkontroluj, zda bezi)",
            "chyba_detaily": str(e)
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)