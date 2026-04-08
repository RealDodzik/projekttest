import os
import json
import requests
import urllib3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

# Vypnutí varování pro SSL (školní server používá interní certifikáty)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# Limit 1MB kvůli omezení školního proxy serveru
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 

UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Načtení nastavení z prostředí
AI_API_KEY = os.getenv("OPENAI_API_KEY", "nenastaveno")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")
AI_MODEL = os.getenv("AI_MODEL", "gemma3:27b")

# --- JEDNODUCHÁ ŠABLONA ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <title>AI Audio Analyzer - Filip Kuba</title>
    <style>
        body { font-family: sans-serif; background: #1a1a2e; color: white; display: flex; justify-content: center; padding-top: 50px; }
        .card { background: #16213e; padding: 30px; border-radius: 15px; width: 400px; text-align: center; border: 1px solid #7209b7; }
        input { margin-bottom: 20px; }
        button { background: #7209b7; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; width: 100%; }
        #res { margin-top: 20px; text-align: left; background: #0f172a; padding: 10px; border-radius: 5px; display: none; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Audio AI Analyzer</h1>
        <p>Limit souboru: 1 MB</p>
        <input type="file" id="file" accept=".wav,.mp3">
        <button onclick="upload()">Analyzovat</button>
        <div id="loading" style="display:none;">⚡ AI pracuje...</div>
        <div id="res"></div>
    </div>

    <script>
    async function upload() {
        const file = document.getElementById("file").files[0];
        if (!file) return alert("Vyber soubor!");
        
        document.getElementById("loading").style.display = "block";
        const form = new FormData();
        form.append("file", file);

        try {
            const res = await fetch("/ai", { method: "POST", body: form });
            const data = await res.json();
            document.getElementById("res").style.display = "block";
            document.getElementById("res").innerHTML = data.error 
                ? `<span style="color:red">Chyba: ${data.error}</span>` 
                : `<strong>Text:</strong> ${data.original_text}<br><br><strong>AI:</strong> ${data.ai_analysis}`;
        } catch (e) {
            alert("Chyba: " + e.message);
        }
        document.getElementById("loading").style.display = "none";
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
    try:
        if "file" not in request.files:
            return jsonify({"error": "Soubor nenalezen"}), 400
        
        f = request.files["file"]
        path = os.path.join(UPLOAD_FOLDER, f.filename)
        f.save(path)

        # 1. PŘEVOD AUDIO -> TEXT (Whisper)
        with open(path, "rb") as audio_file:
            stt_res = requests.post(
                f"{AI_BASE_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                files={"file": audio_file},
                verify=False,
                timeout=30
            )
        
        if stt_res.status_code != 200:
            return jsonify({"error": f"API školy nepodporuje audio (404) nebo je přetížené. Zkus menší soubor. Detail: {stt_res.text}"}), stt_res.status_code

        text = stt_res.json().get("text", "")

        # 2. AI ANALÝZA (Gemma)
        chat_res = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            json={"model": AI_MODEL, "messages": [{"role": "user", "content": f"Shrň tento text: {text}"}]},
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            verify=False
        )
        
        ai_text = chat_res.json()["choices"][0]["message"]["content"]

        return jsonify({"original_text": text, "ai_analysis": ai_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Důležité: Port se musí brát z prostředí
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
