# Subject: googleDetectMenu API görüntüsü — Playwright Chromium önceden kurulu resmi imaj kullanılır.
# Created by: Mapin Data

FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Kalıcı veri klasörleri (docker-compose.yml içinde volume olarak mount edilmesi önerilir)
RUN mkdir -p images logs jobs chrome_scraper_profile

EXPOSE 8003

CMD ["python", "main.py"]
