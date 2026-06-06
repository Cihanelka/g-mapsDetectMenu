"""
API Şemaları — Request/Response modelleri
Created by: Mapin Data
Created at: 2026-04-21
Subject: googleDetecctMenu FastAPI giriş/çıkış veri modelleri.
"""

from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Union


class MapsMenuRequest(BaseModel):
    url: HttpUrl
    id: Optional[str] = None


class MapsMenuResponse(BaseModel):
    url: str
    id: Optional[str] = None
    mekan_adi: Optional[str] = None
    adres: Optional[str] = None
    web_sitesi: Optional[str] = None
    menu_linki: Optional[str] = None
    menu_linkleri: Optional[List[str]] = None
    menu_kaynak: Optional[str] = None   # "maps" | "maps_photo" | None
    sorgu_suresi_saniye: Optional[float] = None


class HealthResponse(BaseModel):
    durum: str
    profil_aktif: bool
    profil_yolu: Optional[str] = None
    zaman: str
