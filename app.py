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

# --- KONFIGURACE ---
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
CORS(app)

AI_API_KEY = os.getenv("AI_API_KEY", "ollama")
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://host.docker.internal:11434/v1")
AI_MODEL = os.getenv("AI_MODEL", "llama3.1")
DB_FILE = os.path.join(base_dir, 'history.json')

UPLOAD_FOLDER = os.path.join(base_dir, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- TVOJE MODERNÍ ŠABLONA (Vložen obsah index.html) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Filip Kuba - Media AI Extractor</title>
    <link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #fcf6f0;
            --card-bg: #ffffff;
            --text-main: #2d2d2d;
            --text-sub: #666666;
            --accent-color: #e67e22;
            --accent-hover: #d35400;
            --border-color: #eee;
            --result-bg: #fffbf2;
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        [data-theme="dark"] {
            --bg-color: #1a1a2e;
            --card-bg: #16213e;
            --text-main: #e9ecef;
            --text-sub: #a2a8d3;
            --accent-color: #7209b7;
            --accent-hover: #560bad;
            --border-color: #24344d;
            --result-bg: #0f172a;
        }
        body { 
            font-family: 'Quicksand', sans-serif; 
            margin: 0; display: flex; justify-content: center; align-items: center;
            min-height: 100vh; background-color: var(--bg-color); color: var(--text-main);
            transition: var(--transition);
        }
        .theme-toggle {
            position: fixed; top: 20px; right: 20px; background: var(--card-bg);
            border: 2px solid var(--accent-color); color: var(--accent-color);
            padding: 10px 15px; border-radius: 50px; cursor: pointer; font-weight: 700;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1); transition: var(--transition);
        }
        .container { 
            background: var(--card-bg); padding: 40px; border-radius: 24px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.08); width: 90%; max-width: 650px; 
            text-align: center; transition: var(--transition);
        }
        h1 { color: var(--accent-color); margin-bottom: 10px; font-weight: 700; font-size: 2.2em; }
        .author { color: var(--text-sub); margin-bottom: 30px; font-weight: 600; }
        .upload-section { border: 2px dashed var(--accent-color); padding: 30px; border-radius: 20px; margin-bottom: 25px; }
        button#btn { 
            background: var(--accent-color); color: white; border: none; padding: 18px 30px; 
            border-radius: 15px; cursor: pointer; font-weight: 700; font-size: 1.2em;
            width: 100%; transition: var(--transition);
        }
        button#btn:hover { background: var(--accent-hover); transform: translateY(-2px); }
        #result { display: none; margin-top: 30px; padding: 25px; background: var(--result-bg); border-radius: 18px; border: 1px solid var(--border-color); text-align: left; }
        .label { font-weight: 700; color: var(--accent-color); text-transform: uppercase; font-size: 0.85em; margin-bottom: 8px; display: block; }
        .content-box { margin-bottom: 20px; line-height: 1.6; }
        .loader { display: none; margin: 20px auto; width: 30px; height: 30px; border: 4px solid var(--border-color); border-top: 4px solid var(--accent-color); border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body data-theme="light">
    <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">🌙 Dark Mode</button>
    <div class="container">
        <h1>Media AI Extractor</h1>
        <p class="author">By Filip Kuba</p>
        <div class="upload-section">
            <input type="file" id="mediaFile" accept=".wav,.mp3,.mp4,.avi,.mov,.mkv">
            <button id="btn" onclick="upload()">Analyzovat soubor</button>
            <div id="loader" class="loader"></div>
            <p id="loadingText" style="display:none; color: var(--accent-color); font-weight: 600;">AI přemýšlí...</p>
        </div>
        <div id="result">
            <span class="label">Média</span>
            <div id="m_type" class="content-box" style="font-weight: 600;"></div>
            <span class="label">Přepis textu</span>
            <div id="o_text" class="content-box"></div>
            <span class="label">AI Insight</span>
            <div id="ai_res" class="content-box" style="background: rgba(0,0,0,0.03); padding: 15px; border-radius: 12px; border-left: 4px solid var(--accent-color);"></div>
        </div>
    </div>
    <script>
        function toggleTheme() {
            const body = document.body;
            const btn = document.getElementById('themeBtn');
            if (body.getAttribute('data-theme') === 'light') {
                body.setAttribute('data-theme', 'dark');
                btn.innerText = "☀️ Light Mode";
            } else {
                body.setAttribute('data-theme', 'light');
                btn.innerText = "🌙 Dark Mode";
            }
        }
        async function upload() {
            const fileInput = document.getElementById('mediaFile');
            const resDiv = document.getElementById('result');
            const loader = document.getElementById('loader');
            const loadText = document.getElementById('loadingText');
            const btn = document.getElementById('btn');
            if (!fileInput.files[0]) return alert("Nejdřív vyber soubor!");
            btn.disabled = true;
            loader.style.display = 'block';
            loadText.style.display = 'block';
            resDiv.style.display = 'none';
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            try {
                const response = await fetch('/ai', { method: 'POST', body: formData });
                const data = await response.json();
                document.getElementById('m_type').innerText = "📁 " + data.media_type;
                document.getElementById('o_text').innerText = data.original_text || "Text nebyl nalezen.";
                document.getElementById('ai_res').innerText = data.ai_analysis;
                resDiv.style.display = 'block';
            } catch (err) {
                alert("Chyba spojení.");
            } finally {
                btn.disabled = false;
                loader.style.display = 'none';
                loadText.style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""

# --- POMOCNÉ FUNKCE ---

def save_to_history(filename, media_type):
    entry = {"timestamp": datetime.datetime.now().isoformat(), "filename": filename, "type": media_type}
    history = []
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: history = json.load(f)
            except: history = []
    history.append(entry)
    with open(DB_FILE, 'w') as f:
        json.dump(history, f, indent=4)

def process_long_audio(file_path):
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

# --- ENDPOINTY ---

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/ai', methods=['POST'])
def process_media():
    if 'file' not in request.files: return jsonify({"error": "Chybí soubor"}), 400
    
    file = request.files['file']
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)
    
    filename = file.filename.lower()
    media_type = "Video File" if filename.endswith(('.mp4', '.avi', '.mov', '.mkv')) else "Audio File"
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

    # PRO FETCH MUSÍ BÝT JSONIFY
    return jsonify({"media_type": media_type, "original_text": text, "ai_analysis": ai_res})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)