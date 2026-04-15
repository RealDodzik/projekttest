# Text Extractor (+AI Insight)
**Autor:** Filip Kuba

Tato webová aplikace postavená na frameworku Flask umožňuje uživatelům nahrávat zvukové soubory ve formátu `.wav`, převádět je na text a následně je nechat analyzovat pomocí umělé inteligence.

## 🚀 Hlavní funkce
* **Audio-to-Text:** Přepis mluveného slova (angličtina) do textové podoby.
* **AI Analýza:** Automatické shrnutí textu nebo identifikace skladby (název/interpret) pomocí modelu Gemma 3.
* **Správa uživatelů:** Systém registrace a přihlašování s bezpečně hashovanými hesly.
* **Historie:** Každý uživatel má přístup k historii svých nahrávek a jejich analýz.
* **Perzistence dat:** Podpora pro ukládání dat do PostgreSQL v Dockeru, která zůstávají zachována i po restartu.

## 🛠 Technologie
* **Backend:** Python (Flask, SQLAlchemy)
* **Databáze:** PostgreSQL (v produkci) / SQLite (pro lokální testování)
* **AI/ML:** SpeechRecognition (Google API), Gemma 3 (přes OpenAI API standard)
* **Frontend:** HTML5, CSS3 (Jinja2 šablony)
* **Deployment:** Docker, Docker Compose

## 📋 Požadavky
* Nainstalovaný **Docker** a **Docker Compose**.
* Přístup k AI API (OpenAI kompatibilní rozhraní).

## 🔧 Konfigurace
Aplikace využívá následující proměnné prostředí (definované v `compose.yml`):
* `OPENAI_API_KEY`: Tvůj klíč k API.
* `OPENAI_BASE_URL`: Adresa API endpointu.
* `SECRET_KEY`: Klíč pro zabezpečení session uživatelů.
* `DATABASE_URL`: Connection string pro připojení k databázi.

## 📦 Spuštění aplikace
Pro spuštění celého stacku (aplikace + databáze) použij příkaz:

```bash
docker-compose up -d --build
