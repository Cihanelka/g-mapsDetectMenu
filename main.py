"""
Uygulama Giriş Noktası
Created by: Mapin Data
Created at: 2026-04-21
Subject: googleDetecctMenu — Adım 1.1 + 1.3 Google Maps menü tespiti API sunucusu başlatıcı.
"""

import uvicorn
import asyncio
import sys

from src.utils.logger import setup_logging

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if __name__ == "__main__":
    _log = setup_logging()
    _log.info("Google Maps Menü Tespiti API Sunucusu Başlatılıyor...")
    host = "0.0.0.0" if sys.platform != "win32" else "127.0.0.1"
    uvicorn.run("src.api.server:app", host=host, port=8003)
