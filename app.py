import os
import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import speech_recognition as sr
from moviepy import VideoFileClip
from pydub import AudioSegment
from pydub.silence import split_on_silence

base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
CORS(app)

# Konfigurace - doma zkus model "llama3.1" (8b) místo "llama3.2:1b"
AI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://host.docker.internal:11434/v1")
AI_MODEL = "gemma3:27b" # Pro domácí testování (před odevzdáním přepni na llama3.2:1b, pokud je server slabý)

UPLOAD_FOLDER = os.path.join(base_dir, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def process_long_audio(file_path):
    """Rozseká dlouhé audio na kousky a přeloží je."""
    sound = AudioSegment.from_file(file_path)
    # Rozdělení podle ticha (min 500ms ticha)
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
            except:
                continue
        os.remove(chunk_path)
    return full_text.strip()

@app.route('/')
def index():
    return send_from_directory(base_dir, 'index.html')

@app.route('/ai', methods=['POST'])
def process_media():
    if 'file' not in request.files:
        return jsonify({"error": "Chybí soubor"}), 400

    file = request.files['file']
    filename = file.filename.lower()
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    # --- DETEKCE TYPU ---
    media_type = "Neznámý"
    is_video = filename.endswith(('.mp4', '.avi', '.mov', '.mkv'))
    is_audio = filename.endswith(('.wav', '.mp3', '.flac', '.m4a'))

    if is_video:
        media_type = "Video File"
        # Extrakce audia z videa
        video = VideoFileClip(file_path)
        audio_path = os.path.join(UPLOAD_FOLDER, "temp_audio.wav")
        video.audio.write_audiofile(audio_path)
        processing_path = audio_path
    else:
        media_type = "Audio File"
        processing_path = file_path

    # --- ZPRACOVÁNÍ TEXTU ---
    try:
        extrahovany_text = process_long_audio(processing_path)
    except Exception as e:
        extrahovany_text = f"Chyba při zpracování: {str(e)}"

    # --- ANALÝZA OBSAHU PŘES AI ---
    prompt = f"""
    Analyzuj následující text: "{extrahovany_text}"
    1. Rozpoznej, zda jde o mluvenou řeč nebo text písně.
    2. Udělej výstižné shrnutí obsahu.
    Odpověz ve formátu:
    TYP OBSAHU: [řeč/píseň]
    SHRNUTÍ: [text]
    """

    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    
    try:
        response = requests.post(f"{AI_BASE_URL.rstrip('/')}/chat/completions", 
                                 json=payload, 
                                 headers={"Authorization": f"Bearer {AI_API_KEY}"}, 
                                 timeout=60)
        ai_res = response.json()['choices'][0]['message']['content']
    except:
        ai_res = "AI analýza selhala."

    return jsonify({
        "media_type": media_type,
        "original_text": extrahovany_text,
        "ai_analysis": ai_res
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)
