import os
import json
import datetime
import requests
import urllib3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import speech_recognition as sr
from moviepy import VideoFileClip
from pydub import AudioSegment
from pydub.silence import split_on_silence

# Ignorovat varování o nezabezpečeném HTTPS (pro školní servery)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- KONFIGURACE ---
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
CORS(app)

# TADY JE TA ZMĚNA: Kód se podívá do systému, jestli tam klíč je. 
# Pokud ho na GitHubu nikdo nevyplní, kód zůstane bezpečný.
AI_API_KEY = os.getenv("OPENAI_API_KEY", "nenastaveno")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://192.168.0.204/v1")
AI_MODEL = os.getenv("AI_MODEL", "llama3.2:1b")

DB_FILE = os.path.join(base_dir, 'history.json')
UPLOAD_FOLDER = os.path.join(base_dir, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ... (zbytek kódu se šablonou a funkcemi zůstává stejný jako minule) ...

@app.route('/')
def home(): return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def status(): return jsonify({"app": "Filip Kuba AI", "status": "online"})

@app.route('/ai', methods=['POST'])
def analyze():
    # Kontrola bezpečnosti - pokud klíč chybí, nepokoušej se o analýzu
    if AI_API_KEY == "nenastaveno":
        return jsonify({"error": "API klíč není nastaven v prostředí serveru"}), 500

    f = request.files['file']
    fp = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(fp)
    
    is_v = f.filename.lower().endswith(('.mp4','.avi','.mov','.mkv'))
    m_type = "Video" if is_v else "Audio"
    
    # Historie
    entry = {"time": str(datetime.datetime.now()), "file": f.filename, "type": m_type}
    h = []
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f_hist: h = json.load(f_hist)
        except: pass
    h.append(entry)
    with open(DB_FILE, 'w') as f_hist: json.dump(h, f_hist, indent=4)

    p_path = fp
    if is_v:
        vid = VideoFileClip(fp)
        p_path = os.path.join(UPLOAD_FOLDER, "temp.wav")
        vid.audio.write_audiofile(p_path)

    text = process_audio(p_path)
    try:
        prompt = f"Shrň tento text jednou větou a urči jestli je to řeč nebo píseň: {text}"
        res = requests.post(f"{AI_BASE_URL.rstrip('/')}/chat/completions", 
                            json={"model": AI_MODEL, "messages": [{"role":"user","content":prompt}], "stream":False}, 
                            headers={"Authorization": f"Bearer {AI_API_KEY}"},
                            verify=False, 
                            timeout=60)
        ai_out = res.json()['choices'][0]['message']['content']
    except Exception as e: ai_out = f"AI nedostupná"

    return jsonify({"media_type": m_type, "original_text": text, "ai_analysis": ai_out})

def process_audio(path):
    sound = AudioSegment.from_file(path)
    chunks = split_on_silence(sound, min_silence_len=500, silence_thresh=sound.dBFS-14)
    rec = sr.Recognizer()
    text = ""
    for i, c in enumerate(chunks):
        cp = os.path.join(UPLOAD_FOLDER, f"c{i}.wav")
        c.export(cp, format="wav")
        with sr.AudioFile(cp) as src:
            audio = rec.record(src)
            try: text += rec.recognize_google(audio, language="cs-CZ") + " "
            except: pass
        if os.path.exists(cp): os.remove(cp)
    return text.strip()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)
