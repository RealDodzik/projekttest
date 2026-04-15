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

# Tajný klíč pro fungování session
app.secret_key = os.getenv("SECRET_KEY", "super_tajny_skolni_klic_123")

# Limit 1MB kvůli školnímu proxy serveru
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 

# Použití perzistentního adresáře pro uploady
UPLOAD_FOLDER = "/data/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Načtení nastavení AI
AI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")
AI_MODEL = "gemma3:27b" 

# --- DATABÁZE ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")
engine = create_engine(DATABASE_URL)

# Čekání na start DB (retry loop)
for i in range(10):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Databáze úspěšně připojena!")
        break
    except Exception:
        print("Čekám na databázi...")
        time.sleep(2)

# Vytvoření tabulek, pokud neexistují
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
    <title>Text Extractor (+AI Insight)</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    
    <script>
        // Okamžité načtení motivu zamezí "probliknutí" při načítání stránky
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>

    <style>
        :root {
            /* Light mode variables */
            --bg-color: #f3f4f6;
            --card-bg: #ffffff;
            --text-main: #1f2937;
            --text-sub: #6b7280;
            --accent-color: #6366f1;
            --accent-hover: #4f46e5;
            --border-color: #e5e7eb;
            --result-bg: #f9fafb;
            --input-bg: #ffffff;
            --error-color: #ef4444;
            --success-color: #10b981;
            --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01);
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        [data-theme="dark"] {
            /* Dark mode variables */
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-sub: #94a3b8;
            --accent-color: #818cf8;
            --accent-hover: #6366f1;
            --border-color: #334155;
            --result-bg: #0f172a;
            --input-bg: #1e293b;
            --shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.25);
        }

        body { 
            font-family: 'Inter', sans-serif; 
            margin: 0; 
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background-color: var(--bg-color); 
            color: var(--text-main);
            padding: 20px;
            box-sizing: border-box;
            transition: background-color 0.3s ease, color 0.3s ease;
        }

        .container { 
            background: var(--card-bg); 
            padding: 40px; 
            border-radius: 20px; 
            box-shadow: var(--shadow); 
            width: 100%;
            max-width: 650px; 
            text-align: center;
            border: 1px solid var(--border-color);
            transition: var(--transition);
        }

        .header-actions {
            position: fixed;
            top: 20px;
            right: 20px;
            display: flex;
            gap: 15px;
            z-index: 1000;
            align-items: center;
        }

        .icon-btn {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            width: 45px;
            height: 45px;
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            cursor: pointer;
            font-size: 1.2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            transition: var(--transition);
        }

        .icon-btn:hover {
            transform: scale(1.05);
            border-color: var(--accent-color);
        }

        h1 { color: var(--text-main); margin-bottom: 5px; font-weight: 700; font-size: 2.2em; letter-spacing: -0.5px; }
        h1 span { color: var(--accent-color); }
        h2 { font-size: 1.2em; color: var(--text-main); margin-top: 30px; font-weight: 600; text-align: left; }
        .author { color: var(--text-sub); margin-bottom: 30px; font-weight: 500; font-size: 0.9em; }

        .form-section, .upload-section { 
            border: 2px dashed var(--border-color); 
            padding: 30px; 
            border-radius: 16px; 
            margin-bottom: 25px; 
            background: var(--result-bg);
            animation: fadeIn 0.5s ease;
            transition: var(--transition);
        }

        .form-section:hover, .upload-section:hover {
            border-color: var(--accent-color);
        }

        input[type="text"], input[type="password"], input[type="file"] {
            margin-bottom: 20px;
            width: 100%;
            box-sizing: border-box;
            color: var(--text-main);
        }

        input[type="text"], input[type="password"] {
            padding: 14px 16px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            background: var(--input-bg);
            font-size: 1em;
            transition: var(--transition);
            outline: none;
        }

        input[type="text"]:focus, input[type="password"]:focus {
            border-color: var(--accent-color);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }

        input[type="file"]::file-selector-button {
            padding: 10px 16px;
            border-radius: 8px;
            border: none;
            background: var(--accent-color);
            color: white;
            font-weight: 600;
            cursor: pointer;
            margin-right: 15px;
            transition: var(--transition);
        }

        input[type="file"]::file-selector-button:hover {
            background: var(--accent-hover);
        }

        button, .btn-link { 
            background: var(--accent-color); 
            color: white; 
            border: none; 
            padding: 14px 30px; 
            border-radius: 12px; 
            cursor: pointer; 
            font-weight: 600; 
            font-size: 1.1em;
            width: 100%; 
            transition: var(--transition);
            text-decoration: none;
            display: inline-block;
            box-shadow: 0 4px 6px -1px rgba(99, 102, 241, 0.4);
        }

        button:hover, .btn-link:hover { 
            background: var(--accent-hover); 
            transform: translateY(-2px); 
            box-shadow: 0 10px 15px -3px rgba(99, 102, 241, 0.5);
        }

        button:disabled {
            background: var(--text-sub);
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .toggle-auth-btn {
            background: transparent;
            border: 2px solid var(--border-color);
            color: var(--text-main);
            padding: 10px 20px;
            border-radius: 50px;
            cursor: pointer;
            font-weight: 600;
            transition: var(--transition);
            text-decoration: none;
            font-size: 0.9em;
            backdrop-filter: blur(10px);
        }

        .toggle-auth-btn:hover {
            border-color: var(--accent-color);
            color: var(--accent-color);
        }

        .history-item { 
            background: var(--result-bg); 
            border: 1px solid var(--border-color); 
            border-radius: 16px; 
            padding: 20px; 
            margin-bottom: 15px; 
            text-align: left;
            transition: var(--transition);
        }

        .history-item:hover {
            border-color: var(--text-sub);
        }

        .label { 
            font-weight: 700; 
            color: var(--accent-color); 
            text-transform: uppercase; 
            font-size: 0.75em; 
            letter-spacing: 0.5px;
            margin-bottom: 8px; 
            display: block; 
        }
        
        .result-box {
            background: var(--input-bg); 
            padding: 16px; 
            border-radius: 12px; 
            margin-bottom: 20px;
            white-space: pre-wrap;
            border: 1px solid var(--border-color);
            font-size: 0.95em;
            line-height: 1.5;
        }

        /* Notifikace - Úspěch a Chyba */
        .msg { padding: 15px; border-radius: 12px; margin-bottom: 20px; font-weight: 600; font-size: 0.95em; animation: fadeIn 0.4s ease; }
        .error-msg { background: rgba(239, 68, 68, 0.1); color: var(--error-color); border: 1px solid rgba(239, 68, 68, 0.2); }
        .success-msg { background: rgba(16, 185, 129, 0.1); color: var(--success-color); border: 1px solid rgba(16, 185, 129, 0.2); }

        hr { border: 0; height: 1px; background: var(--border-color); margin: 15px 0; }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>

    <div class="header-actions">
        <button class="icon-btn" id="themeToggle" onclick="toggleTheme()" title="Přepnout motiv">
            🌙
        </button>
        {% if 'user_id' not in session %}
            <button class="toggle-auth-btn" onclick="toggleAuthSection()" id="authBtn">Vytvořit účet</button>
        {% else %}
            <a href="/logout" class="toggle-auth-btn">Odhlásit se</a>
        {% endif %}
    </div>

    <div class="container">
        <h1>Text Extractor <span>AI</span></h1>
        <p class="author">By Filip Kuba</p>

        {% if error %}
            <div class="msg error-msg">⚠️ {{ error }}</div>
        {% endif %}
        
        {% if success %}
            <div class="msg success-msg">✅ {{ success }}</div>
        {% endif %}

        {% if 'user_id' in session %}
            <div class="upload-section">
                <input type="file" id="mediaFile" accept=".wav">
                <button onclick="upload()" id="btn">Analyzovat soubor</button>
            </div>
            
            <div id="result" style="display:none; text-align: left; margin-top: 25px;">
                <span class="label">Původní přepis z audia</span>
                <div id="orig_text" class="result-box" style="color: var(--text-sub);"></div>

                <span class="label">AI Analýza (English)</span>
                <div id="ai_res" class="result-box" style="border-left: 4px solid var(--accent-color);"></div>
            </div>

            {% if history %}
            <h2>Historie nahrávek</h2>
            {% for item in history %}
                <div class="history-item">
                    <span class="label">{{ item[1] }} • {{ item[4] }}</span>
                    <div style="font-size: 0.9em; color: var(--text-sub); margin-bottom: 12px;">{{ item[2] }}</div>
                    <hr>
                    <div style="font-size: 0.95em;">{{ item[3] }}</div>
                </div>
            {% endfor %}
            {% endif %}

        {% else %}
            <div id="loginSection" class="form-section">
                <h2 style="margin-top: 0; text-align: center;">Přihlášení</h2>
                <form action="/login" method="POST">
                    <input type="text" name="username" placeholder="Uživatelské jméno" required autocomplete="username">
                    <input type="password" name="password" placeholder="Heslo" required autocomplete="current-password">
                    <button type="submit">Vstoupit do aplikace</button>
                </form>
            </div>

            <div id="registerSection" class="form-section" style="display: none;">
                <h2 style="margin-top: 0; text-align: center;">Nová registrace</h2>
                <form action="/register" method="POST">
                    <input type="text" name="username" placeholder="Zvolte si jméno" required autocomplete="username">
                    <input type="password" name="password" placeholder="Zvolte si heslo" required autocomplete="new-password">
                    <button type="submit" style="background: var(--text-main); color: var(--bg-color);">Založit účet</button>
                </form>
            </div>
        {% endif %}
    </div>

    <script>
        // Logika pro tmavý/světlý režim
        function updateThemeIcon() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            document.getElementById('themeToggle').innerText = currentTheme === 'dark' ? '☀️' : '🌙';
        }
        
        function toggleTheme() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon();
        }

        // Inicializace ikonky po načtení DOMu
        document.addEventListener('DOMContentLoaded', updateThemeIcon);

        // Přepínání formulářů
        function toggleAuthSection() {
            const login = document.getElementById('loginSection');
            const register = document.getElementById('registerSection');
            const btn = document.getElementById('authBtn');

            if (login.style.display === 'none') {
                login.style.display = 'block';
                register.style.display = 'none';
                btn.innerText = 'Vytvořit účet';
            } else {
                login.style.display = 'none';
                register.style.display = 'block';
                btn.innerText = 'Zpět na přihlášení';
            }
        }

        async function upload() {
            const fileInput = document.getElementById('mediaFile');
            const btn = document.getElementById('btn');
            const resDiv = document.getElementById('result');
            const origRes = document.getElementById('orig_text');
            const aiRes = document.getElementById('ai_res');

            if (!fileInput.files[0]) {
                alert("⚠️ Vyberte soubor .wav");
                return;
            }

            const formData = new FormData();
            formData.append("file", fileInput.files[0]);

            btn.disabled = true;
            btn.innerText = "⏳ Analyzuji audio...";
            resDiv.style.display = "none";

            try {
                const response = await fetch("/ai", {
                    method: "POST",
                    body: formData
                });

                const data = await response.json();

                if (response.ok) {
                    origRes.innerText = data.original_text;
                    aiRes.innerText = data.ai_analysis;
                    resDiv.style.display = "block";
                } else {
                    alert("Chyba: " + (data.error || "Neznámá chyba"));
                }
            } catch (err) {
                alert("Chyba spojení se serverem.");
            } finally {
                btn.disabled = false;
                btn.innerText = "Analyzovat soubor";
                // Znovu naformátovat formulář po odeslání
                fileInput.value = "";
            }
        }
    </script>
</body>
</html>
"""

# --- ROUTY ---

@app.route("/")
def home():
    # Získání obou zpráv (úspěch i chyba) z URL parametrů
    error = request.args.get("error")
    success = request.args.get("success")
    history_data = []
    
    if 'user_id' in session:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT id, filename, original_text, ai_analysis, TO_CHAR(created_at, 'DD.MM.YYYY HH24:MI') FROM history WHERE user_id = :uid ORDER BY id DESC"),
                {"uid": session['user_id']}
            )
            history_data = result.fetchall()
            
    return render_template_string(HTML_TEMPLATE, history=history_data, error=error, success=success)

@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username")
    password = request.form.get("password")
    
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).fetchone()
        if existing:
            return redirect(url_for('home', error="Uživatelské jméno už existuje."))
        
        hashed_pw = generate_password_hash(password)
        conn.execute(text("INSERT INTO users (username, password_hash) VALUES (:u, :p)"), {"u": username, "p": hashed_pw})
        conn.commit()
        
    # Pokud se to povede, vracíme success parametr
    return redirect(url_for('home', success="Registrace byla úspěšná! Nyní se můžeš přihlásit."))

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    
    with engine.connect() as conn:
        user = conn.execute(text("SELECT id, username, password_hash FROM users WHERE username = :u"), {"u": username}).fetchone()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('home', success=f"Vítej zpět, {username}!"))
        else:
            return redirect(url_for('home', error="Špatné jméno nebo heslo."))

@app.route("/logout")
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('home', success="Byl jsi úspěšně odhlášen."))

@app.route("/ai", methods=["POST"])
def analyze():
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
            text_result = recognizer.recognize_google(audio_data, language="en-US")

        # 2. CHAT ANALÝZA
        chat_res = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            json={
                "model": AI_MODEL, 
                "messages": [{
                    "role": "user", 
                    "content": f"Summarize this text in English. If it's a song, identify title and artist. Otherwise, provide a brief summary: {text_result}"
                }]
            },
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            verify=False,
            timeout=45
        )
        
        if chat_res.status_code != 200:
            return jsonify({"error": f"AI Error: {chat_res.text}"}), chat_res.status_code

        ai_text = chat_res.json()["choices"][0]["message"]["content"]

        # 3. ULOŽENÍ DO DB
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
        return jsonify({"error": "AI nerozuměla nahrávce. Zkus mluvit zřetelněji (anglicky) v .wav souboru."}), 400
    except Exception as e:
        return jsonify({"error": f"Interní chyba: {str(e)}"}), 500
    finally:
        if os.path.exists(path):
            os.remove(path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
