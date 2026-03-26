FROM python:3.9-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install flask requests SpeechRecognition flask-cors

# Kopírování všech souborů (včetně index.html) do kontejneru
COPY . .

EXPOSE 8081

CMD ["python", "app.py"]