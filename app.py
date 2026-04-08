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
AI_MODEL = "gemma3:27b" 

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
            margin: 0; 
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background-color: var(--bg-color); 
            color: var(--text-main);
            transition: var(--transition);
        }

        .theme-toggle {
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--card-bg);
            border: 2px solid var(--accent-color);
            color: var(--accent-color);
            padding: 10px 15px;
            border-radius: 50px;
            cursor: pointer;
            font-weight: 700;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: var(--transition);
            z-index: 1000;
        }
        .theme-toggle:hover { transform: scale(1.05); }

        .container { 
            background: var(--card-bg); 
            padding: 40px; 
            border-radius: 24px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.08); 
            width: 90%;
            max-width: 650px; 
            text-align: center;
            transition: var(--transition);
        }

        h1 { 
            color: var(--accent-color); 
            margin-bottom: 10px;
            font-weight: 700;
            font-size: 2.2em;
        }

        .author { color: var(--text-sub); margin-bottom: 30px; font-weight: 600; }

        .upload-section { 
            border: 2px dashed var(--accent-color); 
            padding: 30px; 
            border-radius: 20px; 
            margin-bottom: 25px; 
            background: rgba(var(--accent-color), 0.05);
        }

        input[type="file"] { 
            margin-bottom: 20px; 
            color: var(--text-main);
            width: 100%;
        }

        button#btn { 
            background: var(--accent-color); 
            color: white; 
            border: none; 
            padding: 18px 30px; 
            border-radius: 15px; 
            cursor: pointer; 
            font-weight: 700; 
            font-size: 1.2em;
            width: 100%; 
            transition: var(--transition);
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        }

        button#btn:hover { 
            background: var(--accent-hover); 
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.2);
        }

        button#btn:disabled { background: #ccc; cursor: not-allowed; transform: none; }

        #result { 
            display: none; 
            margin-top: 30px; 
            padding: 25px; 
            background: var(--result-bg); 
            border-radius: 18px; 
            border: 1px solid var(--border-color);
            text-align: left;
            animation: fadeIn 0.5s ease;
        }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .label { 
            font-weight: 700; 
            color: var(--accent-color); 
            text-transform: uppercase; 
            font-size: 0.85em; 
            letter-spacing: 1px;
            margin-bottom: 8px; 
            display: block; 
        }

        .content-box { margin-bottom: 20px; line-height: 1.6; }
        
        .loader { 
            display: none; 
            margin: 20px auto; 
            width: 30px; height: 30px; 
            border: 4px solid var(--border-color); 
            border-top: 4px solid var(--accent-color); 
            border-radius: 50%; 
            animation: spin 1s linear infinite; 
        }

        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body data-theme="light">

    <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">🌙 Dark Mode</button>

    <div class="container">
        <h1>Media AI Extractor</h1>
        <p class="author">By Filip Kuba</p>
        
        <div class="upload-section">
            <input type="file" id="mediaFile" accept=".wav">
            <button id="btn" onclick="upload()">Analyzovat soubor</button>
            <div id="loader" class="loader"></div>
            <p id="loadingText" style="display:none; color: var(--accent-color); font-weight: 600;">AI přemýšlí...</p>
        </div>

        <div id="result">
            <span class="label">Přípona</span>
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

                if (data.error) {
                    alert("Chyba: " + data.error);
                } else {
                    document.getElementById('m_type').innerText = "📁 " + data.media_type;
                    document.getElementById('o_text').innerText = data.original_text || "Text nebyl nalezen.";
                    document.getElementById('ai_res').innerText = data.ai_analysis;
                    resDiv.style.display = 'block';
                }
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

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/ai", methods=["POST"])
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "Nebyl nahrán žádný soubor"}), 400
    
    f = request.files["file"]
    # Zjistíme příponu pro výpis v UI
    ext = f.filename.split('.')[-1].upper() if '.' in f.filename else "Unknown"
    
    path = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(path)

    try:
        # 1. AUDIO -> TEXT (Lokálně přes SpeechRecognition)
        recognizer = sr.Recognizer()
        with sr.AudioFile(path) as source:
            audio_data = recognizer.record(source)
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
            "media_type": ext,
            "original_text": text,
            "ai_analysis": ai_text
        })

    except sr.UnknownValueError:
        return jsonify({"error": "AI nerozuměla nahrávce. Zkus mluvit zřetelněji a použij soubor .wav."}), 400
    except Exception as e:
        return jsonify({"error": f"Interní chyba: {str(e)}"}), 500
    finally:
        if os.path.exists(path):
            os.remove(path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
