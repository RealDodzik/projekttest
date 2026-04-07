FROM python:3.12-slim

WORKDIR /app

# Kopíruj dependencies
COPY requirements.txt .

# Nainstaluj všechny Python knihovny
RUN pip install --no-cache-dir -r requirements.txt

# Kopíruj celý projekt
COPY . .

# Nastav port z proměnné PORT
CMD ["python", "app.py"]
