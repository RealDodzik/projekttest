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
    <title>Filip Kuba - Text Extractor (+AI Insight)</title>
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

        .header-actions {
            position: fixed;
            top: 20px;
            right: 20px;
            display: flex;
            gap: 10px;
            z-index: 1000;
        }

        h1 { color: var(--accent-color); margin-bottom: 5px; font-weight: 700; font-size: 2.2em; }
        h2 { font-size: 1.2em; color: var(--text-main); margin-top: 10px; border-bottom: 2px solid var(--border-color); padding-bottom: 10px; margin-bottom: 20px;}
        .author { color: var(--text-sub); margin-bottom: 30px; font-weight: 600; }

        .form-section, .upload-section { 
            border: 2px dashed var(--border-color); 
            padding: 30px; 
            border-radius: 20px; 
            margin-bottom: 25px; 
            background: rgba(114, 9, 183, 0.05);
            animation: fadeIn 0.5s ease;
        }

        input[type="text"], input[type="password"], input[type="file"] {
            margin-bottom: 20px;
            width: 100%;
            box-sizing: border-box;
            color: var(--text-main);
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
        }
        button:hover, .btn-link:hover { background: var(--accent-hover); transform: translateY(-2px); }

        .toggle-auth-btn {
            background: var(--card-bg);
            border: 2px solid var(--accent-color);
            color: var(--accent-color);
            padding: 10px 15px;
            border-radius: 50px;
            cursor: pointer;
            font-weight: 700;
            transition: var(--transition);
        }

        .history-item { background: var(--result-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 15px; margin-bottom: 15px; text-align: left;}
        .label { font-weight: 700; color: var(--accent-color); text-transform: uppercase; font-size: 0.85em; margin-bottom: 8px; display: block; }
        
        .error-msg { color: var(--error-color); font-weight: bold; margin-bottom: 15px; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body data-theme="dark">

    <div class="header-actions">
        {% if 'user_id' not in session %}
            <button class="toggle-auth-btn" onclick="toggleAuth()" id="authBtn">📝 Registrace</button>
        {% else %}
            <a href="/logout" class="toggle-auth-btn" style="text-decoration: none;">🚪 Odhlásit</a>
        {% endif %}
    </div>

    <div class="container">
        <h1>Text Extractor (+AI Insight)</h1>
        <p class="author">By Filip Kuba</p>

        {% if error %}
            <div class="error-msg">{{ error }}</div>
        {% endif %}

        {% if 'user_id' in session %}
            <div class="upload-section">
                <input type="file" id="mediaFile" accept=".wav">
                <button onclick="upload()" id="btn">Analyzovat soubor</button>
                <div id="loader" class="loader"></div>
            </div>
            
            <div id="result" style="display:none; text-align: left; margin-top: 20px;">
                <span class="label">Výsledek AI</span>
                <div id="ai_res" style="background: rgba(0,0,0,0.2); padding: 15px; border-radius: 12px;"></div>
            </div>

            <h2>Historie</h2>
            {% for item in history %}
                <div class="history-item">
                    <span class="label">{{ item[1] }}</span>
                    <div>{{ item[3] }}</div>
                </div>
            {% endfor %}

        {% else %}
            <div id="loginSection" class="form-section">
                <h2>Přihlášení</h2>
                <form action="/login" method="POST">
                    <input type="text" name="username" placeholder="Uživatelské jméno" required>
                    <input type="password" name="password" placeholder="Heslo" required>
                    <button type="submit">Vstoupit</button>
                </form>
            </div>

            <div id="registerSection" class="form-section" style="display: none;">
                <h2>Nová registrace</h2>
                <form action="/register" method="POST">
                    <input type="text" name="username" placeholder="Zvolte jméno" required>
                    <input type="password" name="password" placeholder="Zvolte heslo" required>
                    <button type="submit" style="background: #444;">Vytvořit účet</button>
                </form>
            </div>
        {% endif %}
    </div>

    <script>
        function toggleAuth() {
            const login = document.getElementById('loginSection');
            const register = document.getElementById('registerSection');
            const btn = document.getElementById('authBtn');

            if (login.style.display === 'none') {
                login.style.display = 'block';
                register.style.display = 'none';
                btn.innerText = '📝 Registrace';
            } else {
                login.style.display = 'none';
                register.style.display = 'block';
                btn.innerText = '🔑 Přihlášení';
            }
        }

        async function upload() {
            // ... (původní upload funkce zůstává stejná)
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
            text_result = recognizer.recognize_google(audio_data, language="en-US")

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
