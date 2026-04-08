import os
import requests
import urllib3
import speech_recognition as sr
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

# Vypnutí varování pro školní SSL certifikáty
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# Limit 1MB kvůli školnímu proxy serveru
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 

UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Načtení nastavení z dashboardu
AI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")
AI_MODEL = "gemma3:27b" # Model, na který máš oprávnění

# TADY byla ta chybějící proměnná!
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <title>Audio AI Analyzer - Filip Kuba</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: white; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: #16213e; padding: 40px; border-radius: 20px; width: 450px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid #7209b7; }
        h1 { color: #a2a8d3; margin-bottom: 5px; }
        .author { color: #7209b7; font-weight: bold; margin-bottom: 30px; }
        .upload-area { border: 2px dashed #7209b7; padding: 20px; border-radius: 15px; margin-bottom: 20px; background: rgba(114, 9, 183, 0.05); }
        button { background: #7209b7; color: white; border: none; padding: 15px 30px; border-radius: 10px; cursor: pointer; width: 100%; font-size: 16px; font-weight: bold; transition: 0.3s; }
        button:hover { background: #560bad; transform: translateY(-2px); }
        #loading { margin-top: 15px; color: #4cc9f0; display: none; }
        #res { margin-top: 25px; text-align: left; background: #0f172a; padding: 20px; border-radius: 12px; display: none; border-left: 4px solid #7209b7; line-height: 1.6; }
        .error { color: #ff4d4d; font-size: 14px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Audio AI Analyzer</h1>
        <div class="author">By Filip Kuba</div>
        <div class="upload-area">
            <input type="file" id="file" accept=".wav">
            <p style="font-size: 12px; color: #666;">Max. 1 MB, formát .wav</p>
        </div>
        <button onclick="upload()">Analyzovat soubor</button>
        <div id="loading">⚡ AI přemýšlí, vydrž...</div>
        <div id="res">
            <p><strong>📝 Přepis:</strong> <span id="transcription-text"></span></p>
            <p><strong>🤖 AI Analýza:</strong> <span id="analysis-text"></span></p>
        </div>
    </div>

    <script>
    async function upload() {
        const fileInput = document.getElementById("file");
        const file = fileInput.files[0];
        if (!file) return alert("Musíš vybrat soubor!");
        
        const loading = document.getElementById("loading");
        const resDiv = document.getElementById("res");
        
        loading.style.display = "block";
        resDiv.style.display = "none";

        const form = new FormData();
        form.append("file", file);

        try {
            const response = await fetch("/ai", { method: "POST", body: form });
            const data = await response.json();

            if (data.error) {
                alert("Chyba: " + data.error);
            } else {
                document.getElementById("res").style.display = "block";
    
                // Tady JavaScript vezme data z Pythonu a vloží je do SPANů
                // 'data.original_text' v JS musí odpovídat klíči v Pythonu
                document.getElementById("transcription-text").innerText = data.original_text;
                document.getElementById("analysis-text").innerText = data.ai_analysis;
            }
        } catch (e) {
            alert("Kritická chyba: " + e.message);
        } finally {
            loading.style.display = "none";
        }
    }
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/ai", methods=["POST"])
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "Nebyl nahrán žádný soubor"}), 400
    
    f = request.files["file"]
    path = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(path)

    try:
        # 1. AUDIO -> TEXT (Lokálně přes SpeechRecognition, protože Whisper je blokován)
        recognizer = sr.Recognizer()
        with sr.AudioFile(path) as source:
            audio_data = recognizer.record(source)
            # Vyžaduje odchozí internet na Google API
            text = recognizer.recognize_google(audio_data, language="cs-CZ")

        # 2. CHAT ANALÝZA (Školní Gemma)
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
            return jsonify({"error": f"Chyba školní AI (Gemma): {chat_res.text}"}), chat_res.status_code

        ai_text = chat_res.json()["choices"][0]["message"]["content"]

        return jsonify({
            "original_text": text,
            "ai_analysis": ai_text
        })

    except sr.UnknownValueError:
        return jsonify({"error": "AI nerozumněla nahrávce. Zkus mluvit zřetelněji a použij soubor .wav."}), 400
    except Exception as e:
        return jsonify({"error": f"Interní chyba: {str(e)}"}), 500
    finally:
        if os.path.exists(path):
            os.remove(path)

if __name__ == "__main__":
    # Musí poslouchat na portu z proměnné prostředí
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
