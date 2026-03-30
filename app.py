import os
import json
import datetime
import requests
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import speech_recognition as sr
from moviepy import VideoFileClip
from pydub import AudioSegment
from pydub.silence import split_on_silence

# --- KONFIGURACE DLE ZADÁNÍ ---
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
CORS(app)

# Environment proměnné (Bod 3 v zadání)
AI_API_KEY = os.getenv("AI_API_KEY", "ollama")
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://host.docker.internal:11434/v1")
AI_MODEL = os.getenv("AI_MODEL", "llama3.2:1b")
DB_FILE = os.path.join(base_dir, 'history.json') # "Databáze" požadavků

UPLOAD_FOLDER = os.path.join(base_dir, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- POMOCNÉ FUNKCE ---

def save_to_history(filename, media_type):
    """Uloží záznam o zpracování do JSON souboru (Bod 2 v zadání)."""
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "filename": filename,
        "type": media_type
    }
    history = []
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: history = json.load(f)
            except: history = []
    
    history.append(entry)
    with open(DB_FILE, 'w') as f:
        json.dump(history, f, indent=4)

def process_long_audio(file_path):
    """Extrakce textu z audia po kouscích."""
    sound = AudioSegment.from_file(file_path)
    chunks = split_on_silence(sound, min_silence_len=500, silence_thresh=sound.dBFS-14, keep_silence=500)
    recognizer = sr.Recognizer()
    full_text = ""
    for i, chunk in enumerate(chunks):
        chunk_path = os.path.join(UPLOAD_FOLDER, f"chunk{i}.wav")
        chunk.export(chunk_path, format="wav")
        with sr.AudioFile(chunk_path) as source:
            audio = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio, language="cs-CZ")
                full_text += text + " "
            except: continue
        if os.path.exists(chunk_path): os.remove(chunk_path)
    return full_text.strip()

# --- ENDPOINTY (Dle zadání) ---

@app.route('/status', methods=['GET'])
def get_status():
    """Povinná status endpointa (Bod 1 v zadání)."""
    return jsonify({
        "status": "running",
        "model": AI_MODEL,
        "storage": "active",
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/')
def index():
    # Zde zůstává tvůj moderní HTML kód, který jsem ti poslal minule
    return render_template_string(HTML_TEMPLATE) # HTML_TEMPLATE doplň z předchozí zprávy

@app.route('/ai', methods=['POST'])
def process_media():
    if 'file' not in request.files: return jsonify({"error": "Chybí soubor"}), 400
    
    file = request.files['file']
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)
    
    filename = file.filename.lower()
    media_type = "Video File" if filename.endswith(('.mp4', '.avi', '.mov', '.mkv')) else "Audio File"
    
    # Evidence do historie
    save_to_history(file.filename, media_type)

    if media_type == "Video File":
        video = VideoFileClip(file_path)
        audio_path = os.path.join(UPLOAD_FOLDER, "temp_audio.wav")
        video.audio.write_audiofile(audio_path)
        processing_path = audio_path
    else:
        processing_path = file_path

    try:
        text = process_long_audio(processing_path)
        prompt = f"Analyzuj text: '{text}'. Urči zda jde o mluvenou řeč nebo píseň a udělej krátké shrnutí v češtině."
        payload = {"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False}
        r = requests.post(f"{AI_BASE_URL.rstrip('/')}/chat/completions", json=payload, timeout=120)
        ai_res = r.json()['choices'][0]['message']['content']
    except Exception as e:
        ai_res = f"AI analýza selhala: {str(e)}"
        text = text if 'text' in locals() else "Chyba při přepisu."

    return jsonify({"media_type": media_type, "original_text": text, "ai_analysis": ai_res})

if __name__ == '__main__':
    # Běží na portu 8081 dle docker-compose.yml
    app.run(host='0.0.0.0', port=8081)