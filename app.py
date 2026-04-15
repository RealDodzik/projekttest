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


# --- HTML ŠABLONA S JINJA2 (MODERN REHAUL v2) ---
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
            /* --- DARK MODE (Default, Saturated, Deep) --- */
            --bg-1: #040609;
            --bg-2: #0a0f18;
            --bg-3: #020406;
            --card-bg: #0d121f;
            --text-main: #ffffff;
            --text-sub: #8b9bb4;
            /* Sytá neonová fialová/růžová */
            --accent-color: #d02df5; 
            --accent-gradient: linear-gradient(135deg, #d02df5 0%, #810dfa 100%);
            --accent-hover-glow: 0 0 20px rgba(208, 45, 245, 0.7);
            
            --border-color: #1f293a;
            --input-bg: #080b12;
            --result-bg: #040609;
            
            /* Syté barvy notifikací */
            --error-color: #ff3333;
            --success-color: #00e676;
            
            --panel-shadow: 0 15px 35px rgba(0,0,0,0.6);
            --transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }

        [data-theme="light"] {
            /* --- LIGHT MODE (Saturated, Vivid) --- */
            --bg-1: #e0e7ff;
            --bg-2: #f0f4ff;
            --bg-3: #d1d5db;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-sub: #475569;
            /* Sytá modro-fialová */
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

        /* --- Animované pozadí s gradientem --- */
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
            /* Aktivace animace pozadí */
            background: linear-gradient(-45deg, var(--bg-1), var(--bg-2), var(--bg-3), var(--bg-1));
            background-size: 400% 400%;
            animation: gradientBG 15s ease infinite;
            
            color: var(--text-main);
            padding: 20px;
            box-sizing: border-box;
            transition: color 0.3s ease;
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
            backdrop-filter: blur(10px); /* Lehké prosklení */
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

        /* Styl pro switch motivu */
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

        .theme-switch:hover {
            transform: rotate(15deg) scale(1.1);
            border-color: var(--accent-color);
            color: var(--accent-color);
        }

        /* --- SECRET UNICORN --- */
        .unicorn-container {
            position: fixed;
            top: 50%;
            left: -150px;
            font-size: 50px;
            z-index: 9999;
            pointer-events: none;
            display: flex;
            align-items: center;
            filter: drop-shadow(0 0 10px rgba(255, 255, 255, 0.5));
        }

        .rainbow-fart {
            font-size: 30px;
            margin-right: -15px;
        }

        @keyframes run-across {
            0% { transform: translateX(0) translateY(0); }
            25% { transform: translateX(25vw) translateY(-20px); }
            50% { transform: translateX(50vw) translateY(20px); }
            75% { transform: translateX(75vw) translateY(-20px); }
            100% { transform: translateX(calc(100vw + 300px)) translateY(0); }
        }

        .animate-unicorn {
            animation: run-across 5s linear forwards;
        }

        h1 { color: var(--text-main); margin: 0 0 10px 0; font-weight: 700; font-size: 2.6em; letter-spacing: -1.5px; }
        h1 span { background: var(--accent-gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        h2 { font-size: 1.3em; color: var(--text-main); margin-top: 40px; font-weight: 600; text-align: left; letter-spacing: -0.5px;}
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

        .form-section:hover, .upload-section:hover {
            border-color: var(--accent-color);
            box-shadow: 0 0 15px rgba(208, 45, 245, 0.1);
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

        input[type="text"]:focus, input[type="password"]:focus {
            border-color: var(--accent-color);
            box-shadow: 0 0 0 4px rgba(208, 45, 245, 0.15);
            background: var(--input-bg);
        }

        /* Custom styl pro file input */
        .file-input-wrapper { margin-bottom: 25px; text-align: left; }
        input[type="file"] { color: var(--text-sub); font-size: 0.9em; }
        input[type="file"]::file-selector-button {
            padding: 12px 20px;
            border-radius: 10px;
            border: none;
            background: var(--border-color);
            color: var(--text-main);
            font-weight: 600;
            cursor: pointer;
            margin-right: 15px;
            transition: var(--transition);
        }
        input[type="file"]::file-selector-button:hover {
            background: var(--text-sub);
            color: var(--bg-1);
        }

        /* --- ANIMOVANÁ TLAČÍTKA (BOMBA EFFECT) --- */
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
            text-decoration: none;
            display: inline-block;
            box-shadow: 0 4px 6px rgba(208, 45, 245, 0.4);
            position: relative;
            overflow: hidden;
        }

        /* Hover animace buttonu */
        button:hover, .btn-link:hover { 
            transform: translateY(-4px) scale(1.02); 
            /* Pulzující neon záře */
            animation: buttonGlow 1.5s infinite;
        }

        /* Click efekt */
        button:active { transform: translateY(-1px) scale(0.99); }

        button:disabled {
            background: var(--border-color);
            color: var(--text-sub);
            cursor: not-allowed;
            transform: none !important;
            box-shadow: none !important;
            animation: none !important;
        }

        /* Alternativní tlačítko (Registrace/Zpět) */
        .btn-alt {
            background: transparent;
            border: 2px solid var(--border-color);
            color: var(--text-main);
            box-shadow: none;
        }
        .btn-alt:hover {
            background: rgba(255,255,255,0.03);
            border-color: var(--text-sub);
            color: var(--text-main);
            animation: none;
            box-shadow: 0 5px 10px rgba(0,0,0,0.2);
        }

        /* Horní toggle tlačítko */
        .toggle-auth-btn {
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            padding: 12px 24px;
            border-radius: 50px;
            cursor: pointer;
            font-weight: 600;
            transition: var(--transition);
            text-decoration: none;
            font-size: 0.9em;
            backdrop-filter: blur(5px);
        }

        .toggle-auth-btn:hover {
            border-color: var(--accent-color);
            color: var(--accent-color);
            transform: translateY(-2px);
        }

        /* Výsledkové boxy */
        #result { animation: fadeInUp 0.5s ease; }
        .result-item-wrapper { margin-bottom: 25px; text-align: left; }

        .result-box {
            background: var(--bg-1); 
            padding: 20px; 
            border-radius: 16px; 
            white-space: pre-wrap;
            border: 1px solid var(--border-color);
            font-size: 0.95em;
            line-height: 1.6;
            color: var(--text-main);
        }

        /* Historie karty */
        .history-item { 
            background: var(--input-bg); 
            border: 2px solid var(--border-color); 
            border-radius: 18px; 
            padding: 25px; 
            margin-bottom: 20px; 
            text-align: left;
            transition: var(--transition);
            position: relative;
        }

        .history-item:hover {
            border-color: var(--accent-color);
            transform: translateX(5px);
            background: var(--card-bg);
        }

        .history-meta {
            font-size: 0.8em;
            color: var(--accent-color);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
            display: block;
        }

        .history-filename {
            font-weight: 600;
            font-size: 1.1em;
            margin-bottom: 15px;
            color: var(--text-main);
            word-break: break-all;
        }

        .history-text-preview { font-size: 0.9em; color: var(--text-sub); line-height: 1.5; }
        .history-ai-preview { font-size: 0.95em; color: var(--text-main); margin-top: 15px; border-left: 3px solid var(--accent-color); padding-left: 15px;}

        /* --- Syté Notifikace (Flash messages) --- */
        .msg { padding: 18px 25px; border-radius: 14px; margin-bottom: 30px; font-weight: 600; font-size: 1em; animation: fadeInDown 0.4s ease; text-align: left; display: flex; align-items: center; gap: 10px;}
        
        /* Červená pro chybu */
        .error-msg { background: rgba(255, 51, 51, 0.15); color: var(--error-color); border: 2px solid var(--error-color); }
        
        /* Zelená pro úspěch */
        .success-msg { background: rgba(0, 230, 118, 0.15); color: var(--success-color); border: 2px solid var(--success-color); }

        /* Animace */
        @keyframes fadeInDown { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

        /* Loader */
        .loader { display: none; margin: 20px auto; width: 40px; height: 40px; border: 4px solid var(--border-color); border-top: 4px solid var(--accent-color); border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

    </style>
</head>
<body>

    <div class="header-actions">
        <div class="theme-switch" id="themeToggle" onclick="toggleTheme()" title="Přepnout neon/light mód">
            🌙
        </div>
        {% if 'user_id' not in session %}
            <button class="toggle-auth-btn" onclick="toggleAuthSection()" id="authBtn">Vytvořit nový účet</button>
        {% else %}
            <a href="/logout" class="toggle-auth-btn">Odhlásit se</a>
        {% endif %}
    </div>

    <div class="container">
        <h1>Text Extractor <span>AI</span></h1>
        <p class="author">By Filip Kuba</p>

        {# Zobrazení FLASH zpráv (chyby/úspěchy) #}
        {% if error %}
            <div class="msg error-msg"><i>⚠️</i> {{ error }}</div>
        {% endif %}
        
        {% if success %}
            <div class="msg success-msg"><i>✅</i> {{ success }}</div>
        {% endif %}

        {% if 'user_id' in session %}
            {# --- SEKCE PRO PŘIHLÁŠENÉ (UPLOAD) --- #}
            <div class="upload-section">
                <div class="file-input-wrapper">
                    <span class="label">Vyberte nahrávku (.wav)</span>
                    <input type="file" id="mediaFile" accept=".wav">
                </div>
                <button onclick="upload()" id="btn">Analyzovat nahrávku</button>
                <div id="loader" class="loader"></div>
            </div>
            
            {# Výsledky analýzy (skryté do AJAX requestu) #}
            <div id="result" style="display:none; text-align: left;">
                <div class="result-item-wrapper">
                    <span class="label">📁 Původní přepis z audia</span>
                    <div id="orig_text" class="result-box" style="color: var(--text-sub);"></div>
                </div>

                <div class="result-item-wrapper">
                    <span class="label">🤖 AI Insight (English)</span>
                    <div id="ai_res" class="result-box"></div>
                </div>
                <div style="height: 20px;"></div>
            </div>

            {# Historie #}
            {% if history %}
            <h2>Historie tvých analýz</h2>
            {% for item in history %}
                <div class="history-item">
                    <span class="history-meta">Analýza č. {{ item[0] }}</span>
                    <div class="history-filename">{{ item[1] }} <span style="color:var(--text-sub); font-weight:400; font-size:0.8em;">• {{ item[4] }}</span></div>
                    <div class="history-text-preview">{{ item[2] }}</div>
                    <div class="history-ai-preview">{{ item[3] }}</div>
                </div>
            {% endfor %}
            {% endif %}

        {% else %}
            {# --- SEKCE PRO NEPŘIHLÁŠENÉ (LOGIN/REG) --- #}
            <div id="loginSection" class="form-section">
                <h2 style="margin-top: 0; text-align: center; margin-bottom:30px;">Přihlášení</h2>
                <form action="/login" method="POST">
                    <input type="text" name="username" placeholder="Uživatelské jméno" required autocomplete="username">
                    <input type="password" name="password" placeholder="Heslo" required autocomplete="current-password">
                    <button type="submit">Vstoupit do aplikace</button>
                </form>
            </div>

            <div id="registerSection" class="form-section" style="display: none;">
                <h2 style="margin-top: 0; text-align: center; margin-bottom:30px;">Nová registrace</h2>
                <form action="/register" method="POST">
                    <input type="text" name="username" placeholder="Zvolte si uživatelské jméno" required autocomplete="username">
                    <input type="password" name="password" placeholder="Zvolte si bezpečné heslo" required autocomplete="new-password">
                    <button type="submit" class="btn-alt">Vytvořit účet</button>
                </form>
            </div>
        {% endif %}
    </div>

    <script>
        // --- Logika pro Tmavý/Světlý režim (Syté barvy) ---
        function updateThemeIcon() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            // Sluníčko pro tmavý (přepne na světlý), měsíc pro světlý
            document.getElementById('themeToggle').innerText = currentTheme === 'dark' ? '☀️' : '🌙';
        }
        
        function toggleTheme() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme); // Uložení volby
            updateThemeIcon();
        }

        // Inicializace ikonky po načtení
        document.addEventListener('DOMContentLoaded', updateThemeIcon);

        // --- Přepínání formulářů (Login/Register) ---
        function toggleAuthSection() {
            const login = document.getElementById('loginSection');
            const register = document.getElementById('registerSection');
            const btn = document.getElementById('authBtn');

            if (login.style.display === 'none') {
                login.style.display = 'block';
                register.style.display = 'none';
                btn.innerText = 'Vytvořit nový účet';
            } else {
                login.style.display = 'none';
                register.style.display = 'block';
                btn.innerText = 'Zpět na přihlášení';
            }
        }

        function spawnUnicorn() {
            const container = document.createElement('div');
            container.className = 'unicorn-container';
            // Prdící duha následovaná jednorožcem
            container.innerHTML = '<span class="rainbow-fart">🌈</span><span>🦄</span>';
    
            // Náhodná výška, aby neběhal vždycky středem
            container.style.top = Math.random() * 80 + 10 + '%';
    
            document.body.appendChild(container);
            container.classList.add('animate-unicorn');

            // Po doběhnutí ho smažeme, ať nezatěžujeme prohlížeč
            setTimeout(() => {
                container.remove();
            }, 6000);
        }

        // Každou sekundu šance 1/1000
        setInterval(() => {
            if (Math.random() < 0.01) {
                spawnUnicorn();
                console.log("🦄 Secret unicorn spawned!");
            }
        }, 1000);
        // --- AJAX Upload a Analýza ---
        async function upload() {
            const fileInput = document.getElementById('mediaFile');
            const btn = document.getElementById('btn');
            const loader = document.getElementById('loader');
            const resDiv = document.getElementById('result');
            const origRes = document.getElementById('orig_text');
            const aiRes = document.getElementById('ai_res');

            if (!fileInput.files[0]) {
                alert("⚠️ Vyberte prosím soubor ve formátu .wav");
                return;
            }

            const formData = new FormData();
            formData.append("file", fileInput.files[0]);

            // UI State: Loading
            btn.disabled = true;
            btn.innerText = "⏳ Probíhá analýza (může to trvat)...";
            loader.style.display = "block";
            resDiv.style.display = "none";

            try {
                const response = await fetch("/ai", {
                    method: "POST",
                    body: formData
                });

                const data = await response.json();

                if (response.ok) {
                    // Úspěch: Zobrazit výsledky
                    origRes.innerText = data.original_text;
                    aiRes.innerText = data.ai_analysis;
                    resDiv.style.display = "block";
                    
                    // Volitelné: Scroll dolů na výsledek
                    resDiv.scrollIntoView({ behavior: 'smooth' });
                } else {
                    // Chyba ze serveru
                    alert("Chyba: " + (data.error || "Neznámá chyba při analýze."));
                }
            } catch (err) {
                // Chyba sítě
                alert("Chyba: Nelze se spojit se serverem.");
                print(err);
            } finally {
                // UI State: Reset
                btn.disabled = false;
                btn.innerText = "Analyzovat nahrávku";
                loader.style.display = "none";
                fileInput.value = ""; // Vyčistit input
            }
        }
    </script>
</body>
</html>
"""

# --- ROUTY (Backend zůstává stejný, jen přidáváme 'success' do redirectů) ---

@app.route("/")
def home():
    # Získání zpráv z URL parametrů (flash náhrada)
    error = request.args.get("error")
    success = request.args.get("success")
    history_data = []
    
    if 'user_id' in session:
        with engine.connect() as conn:
            # SQL dotaz pro historii (limitován pro přehlednost, řazen sestupně)
            result = conn.execute(
                text("SELECT id, filename, original_text, ai_analysis, TO_CHAR(created_at, 'DD.MM.YYYY HH24:MI') FROM history WHERE user_id = :uid ORDER BY id DESC LIMIT 20"),
                {"uid": session['user_id']}
            )
            history_data = result.fetchall()
            
    return render_template_string(HTML_TEMPLATE, history=history_data, error=error, success=success)

@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username").strip()
    password = request.form.get("password")
    
    if not username or not password:
         return redirect(url_for('home', error="Vyplňte prosím všechna pole."))

    with engine.connect() as conn:
        # Zkontrolovat, zda uživatel už neexistuje
        existing = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).fetchone()
        if existing:
            return redirect(url_for('home', error="Toto uživatelské jméno je již obsazené."))
        
        # Uložit nového s hashem hesla
        hashed_pw = generate_password_hash(password)
        conn.execute(text("INSERT INTO users (username, password_hash) VALUES (:u, :p)"), {"u": username, "p": hashed_pw})
        conn.commit()
        
    # ÚSPĚCH -> zelená zpráva
    return redirect(url_for('home', success="Registrace byla úspěšná! Nyní se můžeš přihlásit."))

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username").strip()
    password = request.form.get("password")
    
    with engine.connect() as conn:
        user = conn.execute(text("SELECT id, username, password_hash FROM users WHERE username = :u"), {"u": username}).fetchone()
        
        # Ověření uživatele a hesla
        if user and check_password_hash(user[2], password):
            # Vytvoření session
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('home', success=f"Vítej zpět, {username}!"))
        else:
            # CHYBA -> červená zpráva
            return redirect(url_for('home', error="Nesprávné uživatelské jméno nebo heslo."))

@app.route("/logout")
def logout():
    # Vyčištění session
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('home', success="Byl jsi úspěšně odhlášen."))

@app.route("/ai", methods=["POST"])
def analyze():
    # API Zabezpečení - jen pro přihlášené
    if 'user_id' not in session:
        return jsonify({"error": "Pro tuto akci musíte být přihlášeni."}), 401

    if "file" not in request.files:
        return jsonify({"error": "Nebyl nahrán žádný soubor."}), 400
    
    f = request.files["file"]
    
    if f.filename == '':
        return jsonify({"error": "Nebyl vybrán žádný soubor."}), 400

    # Sanitize filename a uložení
    safe_filename = "".join([c for c in f.filename if c.isalpha() or c.isdigit() or c==' ' or c=='.' or c=='_']).rstrip()
    ext = safe_filename.split('.')[-1].upper() if '.' in safe_filename else "Unknown"
    
    path = os.path.join(UPLOAD_FOLDER, safe_filename)
    f.save(path)

    try:
        # 1. AUDIO -> TEXT (Převod na text)
        recognizer = sr.Recognizer()
        with sr.AudioFile(path) as source:
            audio_data = recognizer.record(source)
            # Používáme angličtinu, jak bylo nastaveno dříve
            text_result = recognizer.recognize_google(audio_data, language="en-US")

        # 2. CHAT ANALÝZA (AI Shrnutí)
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
            verify=False, # Kvůli školnímu certifikátu
            timeout=60 # Zvýšený timeout pro větší nahrávky
        )
        
        if chat_res.status_code != 200:
            return jsonify({"error": f"Chyba AI modulu: {chat_res.text}"}), chat_res.status_code

        ai_text = chat_res.json()["choices"][0]["message"]["content"]

        # 3. ULOŽENÍ DO DB
        with engine.connect() as conn:
            conn.execute(
                text("INSERT INTO history (user_id, filename, original_text, ai_analysis) VALUES (:uid, :fn, :ot, :ai)"),
                {"uid": session['user_id'], "fn": safe_filename, "ot": text_result, "ai": ai_text}
            )
            conn.commit()

        # Návrat dat pro AJAX
        return jsonify({
            "media_type": ext,
            "original_text": text_result,
            "ai_analysis": ai_text
        })

    except sr.UnknownValueError:
        return jsonify({"error": "AI nerozuměla obsahu nahrávky. Ujistěte se, že je nahrávka čistá a v angličtině."}), 400
    except requests.exceptions.Timeout:
         return jsonify({"error": "Požadavek na AI modul vypršel. Nahrávka je pravděpodobně příliš dlouhá."}), 504
    except Exception as e:
        return jsonify({"error": f"Interní chyba serveru: {str(e)}"}), 500
    finally:
        # Smazání dočasného souboru
        if os.path.exists(path):
            os.remove(path)

if __name__ == "__main__":
    # Spuštění Flask aplikace
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
