"""
FastAPI Uygulama Sunucusu
Created by: Mapin Data
Created at: 2026-04-21
Subject: googleDetecctMenu — Adım 1.1 + 1.3 Google Maps menü tespiti API sunucusu.
"""

import sys
import asyncio
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager

from src.api.routes import router, resumeAllIncompleteJobs
from src.utils.logger import get_logger

_log = get_logger("Server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if sys.platform == "win32":
        loop = asyncio.get_event_loop()
        if not isinstance(loop, asyncio.ProactorEventLoop):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    await resumeAllIncompleteJobs()

    yield
    _log.info("Google Maps Menü Tespiti API Sunucusu Kapatılıyor...")


app = FastAPI(
    title="Google Maps Menü Tespiti API",
    description=(
        "Google Maps URL'sinden menü linki veya menü fotoğraflarını çeker.\n\n"
        "**Adım 1.1**: Maps sayfasından menü linki tespit.\n"
        "**Adım 1.3**: Maps Menü sekmesinden (yoksa kapak fotoğrafından) fotoğraf tarama (Haziran 2024+)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api")


@app.get("/", include_in_schema=False)
def readRoot():
    """Swagger dokümantasyonuna yönlendir."""
    return RedirectResponse(url="/docs")
