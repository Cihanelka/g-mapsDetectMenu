"""
API Route'ları — Google Maps Menü Tespiti Endpoint'leri
Created by: Mapin Data
Created at: 2026-04-21
Subject: Adım 1.1 ve Adım 1.3 pipeline'ını sunan FastAPI endpoint'leri.

Endpoint'ler:
  GET  /health               → Sunucu durumu
  POST /maps-menu            → Tek Maps URL → menü linki veya fotoğraflar
  POST /maps-menu-bulk/start → Excel yükle → toplu işlem başlat
  GET  /maps-menu-bulk/status/{job_id}   → İş durumu ve sonuçlar
  GET  /maps-menu-bulk/download/{job_id} → Sonuçları JSON veya Excel olarak indir
  GET  /history              → Son 50 sorgu geçmişi
"""

import asyncio
import io
import json as _json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from config.settings import MAX_CONCURRENT_SCRAPES
from src.api import state as job_state
from src.api.schemas import HealthResponse, MapsMenuRequest, MapsMenuResponse
from src.scraper.google_maps_scraper import getMenuDataSync, getBulkMenuDataSync
from src.utils.logger import get_logger

import os

_log = get_logger("API")

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SCRAPES)


# ── HEALTH ──────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["Sistem"])
async def healthCheck():
    """Sunucu durumu ve Chrome profili kontrolü."""
    profilPath = os.path.abspath("chrome_scraper_profile")
    profilAktif = os.path.exists(profilPath)
    return HealthResponse(
        durum="ok",
        profil_aktif=profilAktif,
        profil_yolu=profilPath if profilAktif else None,
        zaman=datetime.now().isoformat(),
    )


# ── TEK URL SORGUSU ──────────────────────────────────────────────────────────

@router.post("/maps-menu", tags=["Menü Tespiti"])
async def mapsMenuSingle(request: MapsMenuRequest):
    """
    Tek bir Google Maps URL'si için menü linki veya menü fotoğraflarını döner.

    Pipeline:
      Adım 1.1 → Maps'ten menü linki çek
      Adım 1.3 → Maps Menü butonundan fotoğraf tara

    Response:
      - menu_linki: Menü linki veya ilk fotoğraf URL'si
      - menu_linkleri: Tüm bulunan linkler/fotoğraflar
      - menu_kaynak: "maps" | "maps_photo" | None
    """
    urlStr = str(request.url)
    entryId = request.id or ""

    try:
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        result = await loop.run_in_executor(executor, getMenuDataSync, urlStr, entryId)
        duration = time.perf_counter() - t0

        result["sorgu_suresi_saniye"] = round(duration, 2)

        job_state.addHistory({
            "tip": "maps_menu",
            "url": urlStr,
            "id": entryId or None,
            "mekan_adi": result.get("mekan_adi"),
            "menu_linki": result.get("menu_linki"),
            "menu_kaynak": result.get("menu_kaynak"),
            "sure": round(duration, 2),
            "zaman": datetime.now().isoformat(),
            "basarili": result.get("menu_linki") is not None,
        })

        _log.info(f"Menü tespiti tamamlandı — süre: {duration:.2f}s, kaynak: {result.get('menu_kaynak')}")

        # ID verilmişse {id: menu_linkleri} formatında döndür
        if entryId:
            menuList = result.get("menu_linkleri") or []
            if result.get("menu_linki") and not menuList:
                menuList = [result.get("menu_linki")]
            return {entryId: menuList if len(menuList) > 1 else (menuList[0] if menuList else None)}

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Menü tespiti hatası: {str(e)}")


# ── TOPLU İŞLEM ─────────────────────────────────────────────────────────────

@router.post("/maps-menu-bulk/start", tags=["Menü Tespiti"])
async def mapsMenuBulkStart(file: UploadFile = File(...)):
    """
    Excel yükle → toplu Maps menü tespiti başlat.
    Excel'de 'url' ve opsiyonel 'id' sütunları beklenir.
    """
    if not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Sadece .xls veya .xlsx dosyaları kabul edilir.")

    try:
        import pandas as pd
        import io as _io

        fileBytes = await file.read()
        df = pd.read_excel(_io.BytesIO(fileBytes))

        # URL sütununu bul
        urlCol = None
        for col in df.columns:
            if str(col).strip().lower() in ("url", "maps_url", "google_maps_url", "link"):
                urlCol = col
                break
        if urlCol is None:
            raise ValueError(f"Excel'de 'url' sütunu bulunamadı. Mevcut sütunlar: {list(df.columns)}")

        # ID sütununu bul (opsiyonel)
        idCol = None
        for col in df.columns:
            if str(col).strip().lower() in ("id", "mekan_id", "place_id", "mapin_id"):
                idCol = col
                break

        allUrls = []
        idMap = {}
        placeholderMap = {}

        for i, row in df.iterrows():
            url = row.get(urlCol)
            # ID kolonu varsa kullan, yoksa satır indeksini fallback olarak kullan
            entryId = str(row[idCol]) if idCol and pd.notna(row.get(idCol)) else str(i)

            if pd.isna(url) or not str(url).strip():
                placeholder = f"__bulunmadi_{i}__"
                allUrls.append(placeholder)
                placeholderMap[placeholder] = {"id": entryId, "bulunmadi": True}
            else:
                urlStr = str(url).strip()
                allUrls.append(urlStr)
                idMap[urlStr] = entryId

        validUrls = [u for u in allUrls if not u.startswith("__bulunmadi_")]

        job = job_state.createJob(len(allUrls), urls=allUrls)
        for placeholder, result in placeholderMap.items():
            job_state.updateJob(job.job_id, placeholder, result, isSuccess=False)

        asyncio.create_task(_runBulkMapsJob(job.job_id, validUrls, idMap))

        return {
            "job_id": job.job_id,
            "toplam": len(allUrls),
            "mesaj": (
                f"{len(validUrls)} URL menü tespiti kuyruğuna alındı."
                + (f" ({len(placeholderMap)} satırda URL bulunamadı.)" if placeholderMap else "")
            ),
        }

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Başlatma hatası: {str(e)}")


async def _runBulkMapsJob(jobId: str, urls: list, idMap: dict) -> None:
    """Toplu Maps menü arama arka plan görevi."""

    def onComplete(url: str, data: dict, duration: float) -> None:
        try:
            data["sorgu_suresi_saniye"] = round(duration, 2)
            data["id"] = idMap.get(url)
            isSuccess = data.get("menu_linki") is not None
        except Exception as e:
            _log.error(f"[Job {jobId[:8]}] onComplete hatası: {e}")
            isSuccess = False
        job_state.updateJob(jobId, url, data, isSuccess)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(executor, getBulkMenuDataSync, urls, onComplete, idMap)

    job_state.finishJob(jobId)

    job = job_state.getJob(jobId)
    if job:
        job_state.addHistory({
            "tip": "toplu_maps_menu",
            "mekan_sayisi": job.toplam,
            "basarili": job.tamamlanan,
            "basarisiz": job.basarisiz,
            "zaman": datetime.now().isoformat(),
        })
        _log.info(f"Toplu Maps menü tespiti {jobId} tamamlandı — {job.toplam} mekan")


@router.get("/maps-menu-bulk/status/{job_id}", tags=["Menü Tespiti"])
async def mapsMenuBulkStatus(job_id: str):
    """
    Toplu işlemin durumunu ve (bittiyse) sonuçlarını döner.
    Sonuçlar {id: menu_linki} formatında döner.
    """
    job = job_state.getJob(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="İş bulunamadı.")

    bitti = job.bitis is not None
    tamamlananToplam = job.tamamlanan + job.basarisiz
    gecen = round(
        (job.bitis - job.baslangic if bitti else datetime.now() - job.baslangic).total_seconds(),
        1,
    )

    sonuclarIdBazli = None
    if bitti and job.sonuclar:
        sonuclarIdBazli = {}
        for key, value in job.sonuclar.items():
            if key.startswith("__bulunmadi_"):
                entryId = value.get("id")
                if entryId:
                    sonuclarIdBazli[entryId] = None
            else:
                entryId = value.get("id")
                menuLinki = value.get("menu_linki")
                menuLinkleri = value.get("menu_linkleri") or []
                if entryId:
                    if len(menuLinkleri) > 1:
                        sonuclarIdBazli[entryId] = menuLinkleri
                    elif len(menuLinkleri) == 1:
                        sonuclarIdBazli[entryId] = menuLinkleri[0]
                    elif menuLinki:
                        sonuclarIdBazli[entryId] = menuLinki
                    else:
                        sonuclarIdBazli[entryId] = None

    menuBulunan = 0
    hataDetaylari = {}
    if job.sonuclar:
        menuBulunan = sum(1 for v in job.sonuclar.values() if v.get("menu_linki") is not None)
        for key, value in job.sonuclar.items():
            entryId = value.get("id")
            if entryId and not value.get("menu_linki"):
                if value.get("hata_sebebi"):
                    hataDetaylari[entryId] = value.get("hata_sebebi")
                elif value.get("mekan_adi") is None:
                    hataDetaylari[entryId] = "Mekan adı alınamadı"
                else:
                    hataDetaylari[entryId] = "Hiçbir aşamada menü bulunamadı"

    return {
        "job_id": job_id,
        "toplam": job.toplam,
        "menu_bulunan": menuBulunan,
        "menu_bulunamayan": tamamlananToplam - menuBulunan,
        "hata_detaylari": hataDetaylari if bitti else None,
        "bekleyen": job.toplam - tamamlananToplam,
        "bitti_mi": bitti,
        "gecen_sure_saniye": gecen,
        "yuzde": round(tamamlananToplam / job.toplam * 100) if job.toplam else 0,
        "sonuclar": sonuclarIdBazli if bitti else None,
    }


# ── SONUÇ İNDİRME ───────────────────────────────────────────────────────────

@router.get("/maps-menu-bulk/download/{job_id}", tags=["Menü Tespiti"])
async def mapsMenuBulkDownload(job_id: str, format: str = "json"):
    """
    Tamamlanmış toplu işlemin sonuçlarını indir.

    Query param:
      - format=json  → JSON dosyası (varsayılan)
      - format=excel → Excel (.xlsx) dosyası

    Excel sütunları: id, mekan_adi, menu_linki, menu_linkleri, menu_kaynak, adres
    Resim adları tekli çalışmayla aynı formatta: {id}_{sanitized_url}.jpg
    """
    job = job_state.getJob(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="İş bulunamadı.")
    if job.bitis is None:
        raise HTTPException(status_code=400, detail="İş henüz tamamlanmadı.")

    # ── Sonuçları düzleştir ──
    rows = []
    for key, value in (job.sonuclar or {}).items():
        if key.startswith("__bulunmadi_"):
            rows.append({
                "id": value.get("id"),
                "mekan_adi": None,
                "menu_linki": None,
                "menu_linkleri": None,
                "menu_kaynak": None,
                "adres": None,
            })
        else:
            menuLinkleri = value.get("menu_linkleri") or []
            rows.append({
                "id": value.get("id"),
                "mekan_adi": value.get("mekan_adi"),
                "menu_linki": value.get("menu_linki"),
                "menu_linkleri": ", ".join(menuLinkleri) if menuLinkleri else None,
                "menu_kaynak": value.get("menu_kaynak"),
                "adres": value.get("adres"),
            })

    fmt = format.lower().strip()

    if fmt == "excel":
        import pandas as pd

        df = pd.DataFrame(rows, columns=["id", "mekan_adi", "menu_linki", "menu_linkleri", "menu_kaynak", "adres"])
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Sonuclar")
        buffer.seek(0)
        filename = f"menu_sonuclari_{job_id}.xlsx"
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Varsayılan: JSON
    jsonBytes = _json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"menu_sonuclari_{job_id}.json"
    return StreamingResponse(
        io.BytesIO(jsonBytes),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── GEÇMİŞ ──────────────────────────────────────────────────────────────────

@router.get("/history", tags=["Sistem"])
async def getHistory():
    """Son 50 sorgunun geçmişini döner."""
    return {"gecmis": job_state.getHistory()}
