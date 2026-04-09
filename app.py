import os
import time
import requests
import urllib3
import speech_recognition as sr
from flask import Flask, jsonify, request, render_template_string, session, redirect, url_for
from flask_cors import CORS
from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash, check_password_hash

# Vypnutí varování pro školní SSL certifikáty
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# Tajný klíč pro fungování session (přihlášení)
app.secret_key = os.getenv("SECRET_KEY", "super_tajny_skolni_klic_123")

# Limit 1MB kvůli školnímu proxy serveru
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 

UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Načtení nastavení AI
AI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")
AI_MODEL = "gemma3:27b" 

# --- DATABÁZE ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")
engine = create_engine(DATABASE_URL)

# Čekání na start DB (podle instrukcí učitele)
for i in range(10):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Databáze úspěšně připojena!")
        break
    except Exception:
        print("Čekám na databázi...")
        time.sleep(2)

# Vytvoření tabulek (uživatelé a historie)
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            filename VARCHAR(255),
            original_text TEXT,
            ai_analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.commit()


# --- HTML ŠABLONA S JINJA2 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Audio AI Analyzer</title>
    <link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #1a1a2e;
            --card-bg: #16213e;
            --text-main: #e9ecef;
            --text-sub: #a2a8d3;
            --accent-color: #7209b7;
            --accent-hover: #560bad;
            --border-color: #24344d;
            --result-bg: #0f172a;
            --error-color: #e63946;
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
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
            padding: 20px;
            box-sizing: border-box;
        }

        .container { 
            background: var(--card-bg); 
            padding: 40px; 
            border-radius: 24px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.3); 
            width: 100%;
            max-width: 650px; 
            text-align: center;
        }

        h1 { color: var(--accent-color); margin-bottom: 5px; font-weight: 700; font-size: 2.2em; }
        h2 { font-size: 1.2em; color: var(--text-main); margin-top: 30px; border-bottom: 2px solid var(--border-color); padding-bottom: 10px;}
        .author { color: var(--text-sub); margin-bottom: 30px; font-weight: 600; }

        .upload-section, .form-section { 
            border: 2px dashed var(--border-color); 
            padding: 30px; 
            border-radius: 20px; 
            margin-bottom: 25px; 
            background: rgba(114, 9, 183, 0.05);
        }

        input[type="file"], input[type="text"], input[type="password"] { 
            margin-bottom: 20px; 
            color: var(--text-main);
            width: 100%;
            box-sizing: border-box;
        }

        input[type="text"], input[type="password"] {
            padding: 12px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: var(--bg-color);
        }

        button, .btn-link { 
            background: var(--accent-color); 
            color: white; 
            border: none; 
            padding: 15px 30px; 
            border-radius: 15px; 
            cursor: pointer; 
            font-weight: 700; 
            font-size: 1.1em;
            width: 100%; 
            transition: var(--transition);
            text-decoration: none;
            display: inline-block;
            box-sizing: border-box;
            margin-bottom: 10px;
        }
        button:hover, .btn-link:hover { background: var(--accent-hover); transform: translateY(-2px); }
        button:disabled { background: var(--border-color); cursor: not-allowed; transform: none; }

        .btn-small { padding: 8px 15px; font-size: 0.9em; width: auto; background: var(--border-color); margin-top: 10px; }
        .btn-small:hover { background: #e63946; }

        #result { display: none; margin-top: 30px; padding: 25px; background: var(--result-bg); border-radius: 18px; border: 1px solid var(--border-color); text-align: left; }
        .label { font-weight: 700; color: var(--accent-color); text-transform: uppercase; font-size: 0.85em; margin-bottom: 8px; display: block; }
        .content-box { margin-bottom: 20px; line-height: 1.6; }
        
        .history-item { background: var(--result-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 15px; margin-bottom: 15px; text-align: left;}
        .history-date { font-size: 0.8em; color: var(--text-sub); float: right; }

        .loader { display: none; margin: 20px auto; width: 30px; height: 30px; border: 4px solid var(--border-color); border-top: 4px solid var(--accent-color); border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        .error-msg { color: var(--error-color); font-weight: bold; margin-bottom: 15px; }
    </style>
</head>
<body data-theme="dark">

    <div class="container">
        <h1>Audio AI Analyzer</h1>
        <p class="author">By Filip Kuba</p>

        {% if error %}
            <div class="error-msg">{{ error }}</div>
        {% endif %}

        {% if 'user_id' in session %}
            <div style="text-align: right; margin-bottom: 20px;">
                <span style="color: var(--text-sub);">Přihlášen: <b>{{ session['username'] }}</b></span>
                <a href="/logout" class="btn-link btn-small">Odhlásit se</a>
            </div>

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
                <div id="ai_res" class="content-box" style="background: rgba(0,0,0,0.2); padding: 15px; border-radius: 12px; border-left: 4px solid var(--accent-color);"></div>
            </div>

            <h2>Tvoje historie nahrávek</h2>
            {% if history %}
                {% for item in history %}
                <div class="history-item">
                    <span class="history-date">{{ item[4] }}</span>
                    <span class="label">Soubor: {{ item[1] }}</span>
                    <div style="font-size: 0.9em; margin-bottom: 10px; color: var(--text-sub)"><b>Přepis:</b> {{ item[2][:100] }}...</div>
                    <div style="font-size: 0.95em; border-left: 2px solid var(--accent-color); padding-left: 10px;"><b>AI:</b> {{ item[3] }}</div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: var(--text-sub);">Zatím nemáš žádné záznamy.</p>
            {% endif %}

        {% else %}
            <div class="form-section">
                <h2>Přihlášení</h2>
                <form action="/login" method="POST">
                    <input type="text" name="username" placeholder="Uživatelské jméno" required>
                    <input type="password" name="password" placeholder="Heslo" required>
                    <button type="submit">Přihlásit se</button>
                </form>
            </div>

            <div class="form-section" style="margin-top: 20px;">
                <h2>Nová registrace</h2>
                <form action="/register" method="POST">
                    <input type="text" name="username" placeholder="Nové uživatelské jméno" required>
                    <input type="password" name="password" placeholder="Nové heslo" required>
                    <button type="submit" style="background: var(--border-color); color: var(--text-main);">Zaregistrovat se</button>
                </form>
            </div>
        {% endif %}
    </div>

    <script>
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
                    
                    // Po úspěšné analýze obnovíme stránku za 3 vteřiny, aby se načetla do historie
                    setTimeout(() => window.location.reload(), 3000);
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

# --- ROUTY ---

@app.route("/")
def home():
    error = request.args.get("error")
    history_data = []
    
    # Pokud je uživatel přihlášen, načteme jeho historii
    if 'user_id' in session:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT id, filename, original_text, ai_analysis, TO_CHAR(created_at, 'DD.MM.YYYY HH24:MI') FROM history WHERE user_id = :uid ORDER BY id DESC"),
                {"uid": session['user_id']}
            )
            history_data = result.fetchall()
            
    return render_template_string(HTML_TEMPLATE, history=history_data, error=error)

@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username")
    password = request.form.get("password")
    
    with engine.connect() as conn:
        # Zkontrolovat, zda uživatel už neexistuje
        existing = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).fetchone()
        if existing:
            return redirect(url_for('home', error="Uživatelské jméno už existuje."))
        
        # Uložit nového s hashem hesla
        hashed_pw = generate_password_hash(password)
        conn.execute(text("INSERT INTO users (username, password_hash) VALUES (:u, :p)"), {"u": username, "p": hashed_pw})
        conn.commit()
        
    return redirect(url_for('home', error="Registrace úspěšná! Nyní se přihlas."))

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    
    with engine.connect() as conn:
        user = conn.execute(text("SELECT id, username, password_hash FROM users WHERE username = :u"), {"u": username}).fetchone()
        
        if user and check_password_hash(user[2], password):
            # Přihlášení úspěšné
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('home'))
        else:
            return redirect(url_for('home', error="Špatné jméno nebo heslo."))

@app.route("/logout")
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('home'))

@app.route("/ai", methods=["POST"])
def analyze():
    # Zabezpečení - jen pro přihlášené
    if 'user_id' not in session:
        return jsonify({"error": "Musíš být přihlášený!"}), 401

    if "file" not in request.files:
        return jsonify({"error": "Nebyl nahrán žádný soubor"}), 400
    
    f = request.files["file"]
    ext = f.filename.split('.')[-1].upper() if '.' in f.filename else "Unknown"
    path = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(path)

    try:
        # 1. AUDIO -> TEXT
        recognizer = sr.Recognizer()
        with sr.AudioFile(path) as source:
            audio_data = recognizer.record(source)
            text_result = recognizer.recognize_google(audio_data, language="cs-CZ")

        # 2. CHAT ANALÝZA
        chat_res = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            json={
                "model": AI_MODEL, 
                "messages": [{"role": "user", "content": f"Jednoduše shrň obsah textu. Pokud např. rozpoznáš, že se jedná o text písně, vypiš že se jedná o píseň a pokus se najít název a autora. Pokud nic podobného nerozpoznáš, pouze krátce shrň text: {text_result}"}]
            },
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            verify=False,
            timeout=45
        )
        
        if chat_res.status_code != 200:
            return jsonify({"error": f"Chyba školní AI (Gemma): {chat_res.text}"}), chat_res.status_code

        ai_text = chat_res.json()["choices"][0]["message"]["content"]

        # 3. ULOŽENÍ DO DATABÁZE (Novinka)
        with engine.connect() as conn:
            conn.execute(
                text("INSERT INTO history (user_id, filename, original_text, ai_analysis) VALUES (:uid, :fn, :ot, :ai)"),
                {"uid": session['user_id'], "fn": f.filename, "ot": text_result, "ai": ai_text}
            )
            conn.commit()

        return jsonify({
            "media_type": ext,
            "original_text": text_result,
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
