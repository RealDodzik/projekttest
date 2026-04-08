# 🎙️ Text Extractor (+AI Insight)

Tento projekt je webová aplikace pro převod řeči na text s následnou analýzou pomocí umělé inteligence. Je optimalizován pro běh ve školním prostředí s omezenými prostředky.

## ✨ Hlavní funkce
- **Audio-to-Text**: Převod `.wav` souborů na text pomocí knihovny `SpeechRecognition` (využívá Google API v rámci backendu).
- **AI Analýza**: Automatické generování shrnutí textu pomocí školního API s modelem `gemma3:27b`.
- **Moderní UI**: Responzivní webové rozhraní s přepínatelným **Dark/Light módem**.
- **Optimalizace**: Limit 1MB na soubor pro bezproblémový průchod přes školní proxy server.

## 🛠️ Technické specifikace
- **Backend**: Python 3 (Flask, Flask-CORS)
- **Komunikace**: Requests (s vypnutým ověřováním SSL pro školní certifikáty)
- **Zpracování audia**: SpeechRecognition
- **Frontend**: Vanilla JS (Fetch API) + CSS proměnné pro téma

## 🐳 Deploy na školní server

1️⃣ **Upload**: Nahrajte projekt do svého GitHub repozitáře.  
2️⃣ **Propojení**: Vložte URL repozitáře do školního rozhraní pro nasazení.  
3️⃣ **Konfigurace**: Do polí pro proměnné prostředí (Environment Variables) vložte:

| Proměnná | Popis |
| :--- | :--- |
| `OPENAI_API_KEY` | Váš tajný API klíč pro přístup k modelu |
| `OPENAI_BASE_URL` | `https://kurim.ithope.eu/v1` |

## 📦 Instalace lokálně
Pokud chcete projekt spustit u sebe:
```bash
pip install flask flask-cors requests speechrecognition urllib3
python app.py
