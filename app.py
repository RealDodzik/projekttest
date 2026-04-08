import os
import requests
import urllib3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

# Vypnutí varování pro školní SSL certifikáty
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# Limit 1MB - školní proxy větší soubor nepustí (chyba 413)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 

UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Načtení nastavení (ujisti se, že máš v dashboardu vyplněn OPENAI_API_KEY)
AI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")
AI_MODEL = os.getenv("AI_MODEL", "gemma3:27b")

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
            <input type="file" id="file" accept=".wav,.mp3">
            <p style="font-size: 12px; color: #666;">Max. velikost: 1 MB</p>
        </div>
        <button onclick="upload()">Analyzovat soubor</button>
        <div id="loading">⚡ AI přemýšlí, vydrž...</div>
        <div id="res"></div>
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
            
            resDiv.style.display = "block";
            if (data.error) {
                resDiv.innerHTML = `<div class="error"><strong>Chyba:</strong><br>${data.error}</div>`;
            } else {
                resDiv.innerHTML = `<strong>📝 Přepis:</strong><br>${data.original_text}<br><br><strong>🤖 AI Analýza:</strong><br>${data.ai_analysis}`;
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
        # 1. AUDIO -> TEXT (Doplněn parametr model="whisper-1")
        with open(path, "rb") as audio_file:
            stt_res = requests.post(
                f"{AI_BASE_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                files={"file": audio_file},
                data={"model": "whisper-1"}, # TADY byla ta chyba model=None
                verify=False,
                timeout=45
            )
        
        if stt_res.status_code != 200:
            return jsonify({"error": f"API školy (Audio) vrátilo chybu {stt_res.status_code}: {stt_res.text}"}), stt_res.status_code

        text = stt_res.json().get("text", "")
        if not text:
            return jsonify({"error": "Ze souboru se nepodařilo získat žádný text."}), 400

        # 2. CHAT ANALÝZA
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
        
        ai_text = chat_res.json()["choices"][0]["message"]["content"]

        return jsonify({
            "original_text": text,
            "ai_analysis": ai_text
        })

    except Exception as e:
        return jsonify({"error": f"Nastala chyba na serveru: {str(e)}"}), 500
    finally:
        if os.path.exists(path):
            os.remove(path)

if __name__ == "__main__":
    # Server vyžaduje port z proměnné prostředí PORT
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
