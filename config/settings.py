"""
Uygulama Ayarları
Created by: Mapin Data
Created at: 2026-04-21
Subject: googleDetecctMenu — Adım 1.1 ve 1.3 Google Maps tabanlı menü tespiti için yapılandırma.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Playwright sayfa yükleme timeout'u (ms)
DEFAULT_TIMEOUT = 60000

# FastAPI eş zamanlı scrape limiti
MAX_CONCURRENT_SCRAPES = 10

# Google oturum profili klasörü — setup_session.py ile bir kez oluşturulur
CHROME_PROFILE_DIR = "chrome_scraper_profile"
