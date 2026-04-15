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


# --- HTML ŠABLONA S JINJA2 (MODERN REHAUL v2 + UNICORN) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Text Extractor AI | Filip Kuba</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
    
    <script>
        // Okamžité načtení motivu zamezí "probliknutí"
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>

    <style>
        :root {
            /* --- DARK MODE (Saturated, Deep) --- */
            --bg-1: #040609;
            --bg-2: #0a0f18;
            --bg-3: #020406;
            --card-bg: #0d121f;
            --text-main: #ffffff;
            --text-sub: #8b9bb4;
            --accent-color: #d02df5; 
            --accent-gradient: linear-gradient(135deg, #d02df5 0%, #810dfa 100%);
            --accent-hover-glow: 0 0 20px rgba(208, 45, 245, 0.7);
            --border-color: #1f293a;
            --input-bg: #080b12;
            --result-bg: #040609;
            --error-color: #ff3333;
            --success-color: #00e676;
            --panel-shadow: 0 15px 35px rgba(0,0,0,0.6);
            --transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }

        [data-theme="light"] {
            /* --- LIGHT MODE (Vivid) --- */
            --bg-1: #e0e7ff;
            --bg-2: #f0f4ff;
            --bg-3: #d1d5db;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-sub: #475569;
            --accent-color: #4f46e5;
            --accent-gradient: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            --accent-hover-glow: 0 0 15px rgba(79, 70, 229, 0.5);
            --border-color: #e2e8f0;
            --input-bg: #f8fafc;
            --result-bg: #f1f5f9;
            --error-color: #dc2626;
            --success-color: #16a34a;
            --panel-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }

        @keyframes gradientBG {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        body { 
            font-family: 'Poppins', sans-serif; 
            margin: 0; 
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: linear-gradient(-45deg, var(--bg-1), var(--bg-2), var(--bg-3), var(--bg-1));
            background-size: 400% 400%;
            animation: gradientBG 15s ease infinite;
            color: var(--text-main);
            padding: 20px;
            box-sizing: border-box;
            transition: color 0.3s ease;
            overflow-x: hidden; /* Důležité pro jednorožce */
        }

        .container { 
            background: var(--card-bg); 
            padding: 50px; 
            border-radius: 28px; 
            box-shadow: var(--panel-shadow); 
            width: 100%;
            max-width: 680px; 
            text-align: center;
            border: 1px solid var(--border-color);
            transition: var(--transition);
            backdrop-filter: blur(10px);
            position: relative;
            z-index: 10;
        }

        .header-actions {
            position: fixed;
            top: 25px;
            right: 25px;
            display: flex;
            gap: 15px;
            z-index: 1000;
            align-items: center;
        }

        .theme-switch {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            cursor: pointer;
            font-size: 1.3rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
            transition: var(--transition);
        }

        .theme-switch:hover { transform: rotate(15deg) scale(1.1); border-color: var(--accent-color); color: var(--accent-color); }

        h1 { color: var(--text-main); margin: 0 0 10px 0; font-weight: 700; font-size: 2.6em; letter-spacing: -1.5px; }
        h1 span { background: var(--accent-gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        .author { color: var(--text-sub); margin-bottom: 40px; font-weight: 400; font-size: 0.95em; opacity: 0.8; }

        .form-section, .upload-section { 
            border: 2px solid var(--border-color); 
            padding: 35px; 
            border-radius: 20px; 
            margin-bottom: 30px; 
            background: var(--input-bg);
            animation: fadeInDown 0.5s ease;
            transition: var(--transition);
        }

        input[type="text"], input[type="password"] {
            padding: 16px 20px;
            border-radius: 14px;
            border: 2px solid var(--border-color);
            background: var(--bg-1);
            font-size: 1em;
            color: var(--text-main);
            transition: var(--transition);
            outline: none;
            margin-bottom: 20px;
            width: 100%;
            box-sizing: border-box;
        }

        input[type="text"]:focus, input[type="password"]:focus { border-color: var(--accent-color); box-shadow: 0 0 0 4px rgba(208, 45, 245, 0.15); }

        @keyframes buttonGlow {
            0% { box-shadow: 0 4px 6px rgba(208, 45, 245, 0.4); }
            50% { box-shadow: 0 4px 25px rgba(208, 45, 245, 0.7); }
            100% { box-shadow: 0 4px 6px rgba(208, 45, 245, 0.4); }
        }

        button, .btn-link { 
            background: var(--accent-gradient); 
            color: white; 
            border: none; 
            padding: 16px 35px; 
            border-radius: 14px; 
            cursor: pointer; 
            font-weight: 700; 
            font-size: 1.1em;
            width: 100%; 
            transition: var(--transition);
            box-shadow: 0 4px 6px rgba(208, 45, 245, 0.4);
        }

        button:hover:not(:disabled) { transform: translateY(-4px) scale(1.02); animation: buttonGlow 1.5s infinite; }
        button:disabled { background: var(--border-color); cursor: not-allowed; opacity: 0.6; }

        .msg { padding: 18px 25px; border-radius: 14px; margin-bottom: 30px; font-weight: 600; animation: fadeInDown 0.4s ease; text-align: left; }
        .error-msg { background: rgba(255, 51, 51, 0.1); color: var(--error-color); border: 1px solid var(--error-color); }
        .success-msg { background: rgba(0, 230, 118, 0.1); color: var(--success-color); border: 1px solid var(--success-color); }

        /* --- SECRET UNICORN STYLES --- */
        .unicorn-container {
            position: fixed;
            top: 50%;
            left: -150px;
            font-size: 60px;
            z-index: 9999;
            pointer-events: none;
            display: flex;
            align-items: center;
            filter: drop-shadow(0 0 15px rgba(255, 255, 255, 0.6));
        }
        .rainbow-fart { font-size: 40px; margin-right: -10px; }
        @keyframes run-across {
            0% { transform: translateX(0) translateY(0) rotate(0deg); }
            25% { transform: translateX(25vw) translateY(-30px) rotate(5deg); }
            50% { transform: translateX(50vw) translateY(30px) rotate(-5deg); }
            75% { transform: translateX(75vw) translateY(-30px) rotate(5deg); }
            100% { transform: translateX(calc(100vw + 300px)) translateY(0) rotate(0deg); }
        }
        .animate-unicorn { animation: run-across 5s linear forwards; }

        @keyframes fadeInDown { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>

    <div class="header-actions">
        <div class="theme-switch" id="themeToggle" onclick="toggleTheme()">🌙</div>
        {% if 'user_id' not in session %}
            <button class="toggle-auth-btn" style="width:auto; padding: 10px 20px;" onclick="toggleAuthSection()" id="authBtn">Vytvořit účet</button>
        {% else %}
            <a href="/logout" style="text-decoration:none;"><button style="width:auto; padding: 10px 20px;">Odhlásit se</button></a>
        {% endif %}
    </div>

    <div class="container">
        <h1>Text Extractor <span>AI</span></h1>
        <p class="author">By Filip Kuba</p>

        {% if error %}<div class="msg error-msg">⚠️ {{ error }}</div>{% endif %}
        {% if success %}<div class="msg success-msg">✅ {{ success }}</div>{% endif %}

        {% if 'user_id' in session %}
            <div class="upload-section">
                <input type="file" id="mediaFile" accept=".wav" style="margin-bottom:20px;">
                <button onclick="upload()" id="btn">Analyzovat nahrávku</button>
            </div>
            
            <div id="result" style="display:none; text-align: left; background: var(--input-bg); padding: 20px; border-radius: 15px;">
                <h3 style="color:var(--accent-color)">Výsledek:</h3>
                <p id="orig_text" style="color:var(--text-sub)"></p>
                <hr style="border:0; border-top:1px solid var(--border-color)">
                <p id="ai_res" style="font-weight:500"></p>
            </div>
        {% else %}
            <div id="loginSection" class="form-section">
                <form action="/login" method="POST">
                    <input type="text" name="username" placeholder="Uživatelské jméno" required>
                    <input type="password" name="password" placeholder="Heslo" required>
                    <button type="submit">Přihlásit se</button>
                </form>
            </div>
            <div id="registerSection" class="form-section" style="display: none;">
                <form action="/register" method="POST">
                    <input type="text" name="username" placeholder="Nové jméno" required>
                    <input type="password" name="password" placeholder="Nové heslo" required>
                    <button type="submit" style="background:var(--border-color)">Zaregistrovat</button>
                </form>
            </div>
        {% endif %}
    </div>

    <script>
        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme');
            const target = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', target);
            localStorage.setItem('theme', target);
            document.getElementById('themeToggle').innerText = target === 'dark' ? '☀️' : '🌙';
        }

        function toggleAuthSection() {
            const login = document.getElementById('loginSection');
            const reg = document.getElementById('registerSection');
            const btn = document.getElementById('authBtn');
            if(login.style.display === 'none') {
                login.style.display = 'block'; reg.style.display = 'none'; btn.innerText = 'Vytvořit účet';
            } else {
                login.style.display = 'none'; reg.style.display = 'block'; btn.innerText = 'Zpět na přihlášení';
            }
        }

        async function upload() {
            const fileInput = document.getElementById('mediaFile');
            if (!fileInput.files[0]) { alert("Vyberte .wav soubor"); return; }
            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            
            const btn = document.getElementById('btn');
            btn.disabled = true; btn.innerText = "Analyzuji...";

            try {
                const res = await fetch("/ai", { method: "POST", body: formData });
                const data = await res.json();
                if (res.ok) {
                    document.getElementById('result').style.display = 'block';
                    document.getElementById('orig_text').innerText = data.original_text;
                    document.getElementById('ai_res').innerText = data.ai_analysis;
                } else { alert(data.error); }
            } catch (e) { alert("Chyba serveru"); }
            finally { btn.disabled = false; btn.innerText = "Analyzovat nahrávku"; }
        }

        /* --- SECRET UNICORN LOGIC --- */
        function spawnUnicorn() {
            const container = document.createElement('div');
            container.className = 'unicorn-container';
            container.innerHTML = '<span class="rainbow-fart">🌈</span><span>🦄</span>';
            container.style.top = (Math.random() * 70 + 15) + '%';
            document.body.appendChild(container);
            container.classList.add('animate-unicorn');
            setTimeout(() => { container.remove(); }, 6000);
        }

        setInterval(() => {
            if (Math.random() < 0.001) { // 1/1000 šance každou sekundu
                spawnUnicorn();
                console.log("🦄 Lucky you! Unicorn appeared.");
            }
        }, 1000);
    </script>
</body>
</html>
"""

# --- BACKEND LOGIC ---

@app.route("/")
def home():
    error = request.args.get("error")
    success = request.args.get("success")
    history_data = []
    if 'user_id' in session:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT id, filename, original_text, ai_analysis, created_at FROM history WHERE user_id = :uid ORDER BY id DESC LIMIT 10"), {"uid": session['user_id']})
            history_data = result.fetchall()
    return render_template_string(HTML_TEMPLATE, history=history_data, error=error, success=success)

@app.route("/register", methods=["POST"])
def register():
    u, p = request.form.get("username"), request.form.get("password")
    with engine.connect() as conn:
        if conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": u}).fetchone():
            return redirect(url_for('home', error="Jméno obsazeno"))
        conn.execute(text("INSERT INTO users (username, password_hash) VALUES (:u, :p)"), {"u": u, "p": generate_password_hash(p)})
        conn.commit()
    return redirect(url_for('home', success="Registrace OK"))

@app.route("/login", methods=["POST"])
def login():
    u, p = request.form.get("username"), request.form.get("password")
    with engine.connect() as conn:
        user = conn.execute(text("SELECT id, username, password_hash FROM users WHERE username = :u"), {"u": u}).fetchone()
        if user and check_password_hash(user[2], p):
            session['user_id'], session['username'] = user[0], user[1]
            return redirect(url_for('home', success=f"Ahoj {u}"))
    return redirect(url_for('home', error="Chyba přihlášení"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home', success="Odhlášeno"))

@app.route("/ai", methods=["POST"])
def analyze():
    if 'user_id' not in session: return jsonify({"error": "Nepřihlášen"}), 401
    f = request.files.get("file")
    if not f: return jsonify({"error": "Žádný soubor"}), 400
    
    path = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(path)
    try:
        rec = sr.Recognizer()
        with sr.AudioFile(path) as src:
            audio = rec.record(src)
            text_out = rec.recognize_google(audio, language="en-US")
        
        ai_call = requests.post(f"{AI_BASE_URL}/chat/completions",
            json={"model": AI_MODEL, "messages": [{"role": "user", "content": f"Summarize: {text_out}"}]},
            headers={"Authorization": f"Bearer {AI_API_KEY}"}, verify=False)
        ai_res = ai_call.json()["choices"][0]["message"]["content"]

        with engine.connect() as conn:
            conn.execute(text("INSERT INTO history (user_id, filename, original_text, ai_analysis) VALUES (:uid, :fn, :ot, :ai)"),
                {"uid": session['user_id'], "fn": f.filename, "ot": text_out, "ai": ai_res})
            conn.commit()
        return jsonify({"original_text": text_out, "ai_analysis": ai_res})
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: 
        if os.path.exists(path): os.remove(path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
