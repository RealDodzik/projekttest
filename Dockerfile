FROM python:3.9-slim

# Instalace ffmpeg pro zpracování audia/videa
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Nejdřív zkopírujeme requirements a nainstalujeme je
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pak zkopírujeme zbytek projektu
COPY . .

EXPOSE 8081

CMD ["python", "app.py"]