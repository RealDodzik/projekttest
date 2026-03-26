FROM python:3.9-slim

# Instalace ffmpeg pro podporu zpracování audia
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalace Python knihoven
RUN pip install flask requests SpeechRecognition flask-cors

COPY app.py .

# Aplikace naslouchá na portu 8081
EXPOSE 8081

CMD ["python", "app.py"]