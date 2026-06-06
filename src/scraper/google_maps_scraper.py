"""
Google Maps Menü Scraper — Adım 1.1 + Adım 1.3 Pipeline
Created by: Mapin Data
Created at: 2026-04-21
Subject: Google Maps URL'sinden menü linki veya menü fotoğraflarını çeken pipeline.

Pipeline akışı:
  1.1 Maps menü linki → bulunursa döndür
  1.3 Maps Menü butonu fotoğraf tarama → bulunursa döndür
  Bulunamazsa → None

Bu modül; Adım 1.2 (web sitesi tarama) ve Adım 1.4 (browser-use AI arama)
içermez — bunlar detectMenu projesinde yürütülür.
"""

import asyncio
import os
import random
import re
import time

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from config.settings import DEFAULT_TIMEOUT, CHROME_PROFILE_DIR
from src.scraper.browser_config import _PROFILE_LOCK, _STEALTH_INIT_SCRIPT, _CONTEXT_KWARGS, COMMON_LAUNCH_ARGS
from src.scraper.menu_link_extractor import get_all_menu_links
from src.scraper.menu_photo_extract import extractMenuFromPhotos
from src.utils.scraper_utils import clickCookieIfAny, cleanText, safeText, safeAttr, safeHref
from src.utils.logger import get_logger

_log = get_logger("GoogleMapsScraper")


# ── GOOGLE OTURUM ISITMA ──────────────────────────────────────────────────────

async def _warmUpGoogleSession(page) -> None:
    """
    Google ana sayfasını ziyaret ederek NID / SOCS cookie'lerini alır ve
    consent (rıza) popup'ını kabul eder.
    Bu adım Maps'in tam içeriği (menü butonu dahil) göstermesi için gereklidir;
    cookie olmayan yeni oturumlarda Maps bazı UI elemanlarını gizler.
    """
    try:
        _log.info("Google ön ziyareti başlatılıyor (cookie ısınması)...")
        await page.goto("https://www.google.com", timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(random.randint(1500, 2500))
        await clickCookieIfAny(page)
        await page.wait_for_timeout(random.randint(800, 1200))
        _log.info("Google ön ziyareti tamamlandı")
    except Exception as e:
        _log.warning(f"Google ön ziyareti başarısız (devam ediliyor): {e}")


# ── MAPS VERİ ÇEKME ──────────────────────────────────────────────────────────

async def _extractMapsData(page, url: str, attemptLabel: str) -> dict:
    """
    Google Maps sayfasından mekan adı, adres, web sitesi ve menü linklerini çeker.
    Hafif extraction — sadece gerekli verileri çeker.

    Returns:
        {
            "mekan_adi": str | None,
            "adres": str | None,
            "web_sitesi": str | None,
            "menu_linki": str | None,
            "menu_linkleri": list[str] | None,
        }
    """
    data = {
        "mekan_adi": None,
        "adres": None,
        "web_sitesi": None,
        "menu_linki": None,
        "menu_linkleri": [],
    }

    try:
        _log.info(f"[{attemptLabel}] Sayfa yükleniyor: {url}")
        await page.goto(url, timeout=DEFAULT_TIMEOUT, wait_until="domcontentloaded")

        await page.wait_for_timeout(random.randint(4000, 6000))
        await clickCookieIfAny(page)
        await page.wait_for_timeout(random.randint(500, 800))

        # Yönlendirme kontrolü
        currentUrl = page.url
        if "google.com/maps" not in currentUrl:
            _log.warning(f"[{attemptLabel}] Yönlendirme tespit edildi, geri dönülüyor...")
            await page.goto(url, timeout=DEFAULT_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(4000, 6000))
            await clickCookieIfAny(page)

        # Minimal fare hareketi (bot tespitini engellemek için)
        await page.mouse.move(
            random.randint(300, 800), random.randint(200, 500),
            steps=random.randint(3, 6),
        )
        await page.wait_for_timeout(random.randint(200, 400))

        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        # ── Mekan adı ──
        try:
            await page.wait_for_selector("h1", timeout=10000)
            h1 = page.locator("h1").first
            if await h1.count() > 0 and await h1.is_visible():
                data["mekan_adi"] = cleanText(await h1.inner_text())
        except Exception:
            pass

        if not data["mekan_adi"]:
            _log.warning(f"[{attemptLabel}] Mekan adı alınamadı")
            return data

        _log.info(f"[{attemptLabel}] Mekan adı: {data['mekan_adi']}")

        # ── Maps sidebar scroll — menü butonu lazy load ile geliyor ──
        try:
            scrolled = await page.evaluate("""() => {
                const h1 = document.querySelector('h1');
                if (!h1) return false;
                let el = h1.parentElement;
                for (let i = 0; i < 12; i++) {
                    if (!el) break;
                    const style = window.getComputedStyle(el);
                    const overflow = style.overflowY;
                    if ((overflow === 'auto' || overflow === 'scroll') && el.scrollHeight > el.clientHeight) {
                        el.scrollBy(0, 500);
                        return true;
                    }
                    el = el.parentElement;
                }
                const selectors = ['div[aria-label][tabindex="-1"]', '.DxyBCb', '.m6QErb', '[jsaction*="scroll"]'];
                for (const sel of selectors) {
                    const found = document.querySelector(sel);
                    if (found && found.scrollHeight > found.clientHeight) {
                        found.scrollBy(0, 500);
                        return true;
                    }
                }
                return false;
            }""")
            _log.debug(f"Scroll sonucu: {scrolled}")
            await page.wait_for_timeout(random.randint(800, 1200))
            await page.mouse.wheel(0, 500)
            await page.wait_for_timeout(random.randint(600, 900))
        except Exception as scrollErr:
            _log.debug(f"Scroll hatası: {scrollErr}")

        # ── Menü linkleri (Adım 1.1 ana hedef) ──
        allMenuLinks = await get_all_menu_links(page)
        if allMenuLinks:
            data["menu_linki"] = allMenuLinks[0]
            data["menu_linkleri"] = allMenuLinks
            _log.info(f"[{attemptLabel}] {len(allMenuLinks)} menü linki bulundu: {allMenuLinks}")
        else:
            data["menu_linkleri"] = []

        # ── Adres (log ve dışa aktarım için) ──
        for sel in [
            '[data-item-id^="address"] .Io6YTe',
            '[data-item-id^="address"] .rogA2c',
            'button[data-item-id^="address"]',
        ]:
            txt = await safeText(page.locator(sel).first)
            if txt:
                data["adres"] = txt
                break

        if not data["adres"]:
            for sel in ['button[aria-label*="Adres"]', 'button[aria-label*="Address"]']:
                aria = await safeAttr(page.locator(sel).first, "aria-label")
                if aria:
                    cleaned = re.sub(r'^(Adres|Address)\s*[:\-]?\s*', '', aria, flags=re.I).strip()
                    if cleaned:
                        data["adres"] = cleaned
                        break

        # ── Web sitesi ──
        for sel in [
            'a[aria-label="Web sitesini aç"]',
            'a[aria-label="Open website"]',
            'a[data-item-id^="authority"]',
            '[data-item-id^="authority"] a',
            'a[aria-label*="Web sitesi"]',
            'a[aria-label*="Website"]',
        ]:
            href = await safeHref(page.locator(sel).first)
            if href and href.startswith("http") and "google.com" not in href:
                data["web_sitesi"] = href
                break

        _log.info(
            f"[{attemptLabel}] Tamamlandı — "
            f"menü: {bool(data['menu_linki'])}, "
            f"adres: {bool(data['adres'])}, "
            f"web_sitesi: {bool(data['web_sitesi'])}"
        )

    except PlaywrightTimeoutError:
        _log.error(f"[{attemptLabel}] Timeout!")
    except Exception as e:
        _log.error(f"[{attemptLabel}] Hata: {e}", exc_info=True)

    return data


# ── ANA PIPELINE ─────────────────────────────────────────────────────────────

async def _runGoogleMapsPipeline(url: str, entryId: str = "") -> dict:
    """
    Tek URL için Adım 1.1 → Adım 1.3 pipeline'ını çalıştırır.

    Adım 1.1: Maps'ten menü linki çek → bulunursa döndür
    Adım 1.3: Maps Menü butonundan fotoğraf tara → bulunursa döndür

    Args:
        url: Google Maps URL
        entryId: Mekan ID'si (fotoğraf dosya adı için: id_tamurl)

    Returns:
        {
            "url": str,
            "mekan_adi": str | None,
            "adres": str | None,
            "web_sitesi": str | None,
            "menu_linki": str | None,       # İlk menü linki veya ilk fotoğraf URL'si
            "menu_linkleri": list | None,   # Tüm bulunan linkler/fotoğraflar
            "menu_kaynak": "maps" | "maps_photo" | None,
        }
    """
    result = {
        "url": url,
        "mekan_adi": None,
        "adres": None,
        "web_sitesi": None,
        "menu_linki": None,
        "menu_linkleri": None,
        "menu_kaynak": None,
    }

    chromeProfile = os.path.abspath(CHROME_PROFILE_DIR)
    isProfileExists = os.path.exists(chromeProfile)

    mapsPage = None
    cleanup = None

    # ── Browser başlat (profil varsa → profil ile, yoksa anonim) ──
    if isProfileExists:
        _log.info("Profil kilidi bekleniyor...")
        with _PROFILE_LOCK:
            _log.debug(f"Profil kullanılıyor: {chromeProfile}")
            p = await async_playwright().start()
            try:
                ctx = await p.chromium.launch_persistent_context(
                    user_data_dir=chromeProfile,
                    channel="chrome",
                    headless=True,
                    args=COMMON_LAUNCH_ARGS,
                    ignore_default_args=["--enable-automation"],
                    viewport={"width": 1440, "height": 900},
                    locale="tr-TR",
                    timezone_id="Europe/Istanbul",
                    extra_http_headers={"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"},
                )
            except Exception:
                ctx = await p.chromium.launch_persistent_context(
                    user_data_dir=chromeProfile,
                    headless=True,
                    args=COMMON_LAUNCH_ARGS,
                    ignore_default_args=["--enable-automation"],
                    viewport={"width": 1440, "height": 900},
                    locale="tr-TR",
                    timezone_id="Europe/Istanbul",
                    extra_http_headers={"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"},
                )

            await ctx.add_init_script(_STEALTH_INIT_SCRIPT)
            mapsPage = await ctx.new_page()

            async def cleanupProfil():
                try:
                    await ctx.close()
                except Exception:
                    pass
                try:
                    await p.stop()
                except Exception:
                    pass

            cleanup = cleanupProfil
    else:
        _log.info("Profil yok — anonim modda çalışılıyor")
        p = await async_playwright().start()
        try:
            browser = await p.chromium.launch(channel="chrome", headless=True, args=COMMON_LAUNCH_ARGS)
        except Exception:
            browser = await p.chromium.launch(headless=True, args=COMMON_LAUNCH_ARGS)

        context = await browser.new_context(**_CONTEXT_KWARGS)
        await context.add_init_script(_STEALTH_INIT_SCRIPT)
        mapsPage = await context.new_page()
        await _warmUpGoogleSession(mapsPage)

        async def cleanupAnonim():
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await p.stop()
            except Exception:
                pass

        cleanup = cleanupAnonim

    try:
        # ── ADIM 1.1: Maps'ten menü linki çek ──
        _log.info(f"[1.1] BAŞLIYOR — Maps'ten menü linki aranıyor: {url}")
        mapsData = await _extractMapsData(mapsPage, url, "maps")
        result["mekan_adi"] = mapsData.get("mekan_adi")
        result["adres"] = mapsData.get("adres")
        result["web_sitesi"] = mapsData.get("web_sitesi")

        if mapsData.get("menu_linki"):
            result["menu_linki"] = mapsData["menu_linki"]
            result["menu_linkleri"] = mapsData.get("menu_linkleri") or [mapsData["menu_linki"]]
            result["menu_kaynak"] = "maps"
            _log.info(f"[1.1] BASARILI — menü linki Maps'ten bulundu: {result['menu_linki']}")
            return result

        _log.info("[1.1] BASARISIZ — Maps'te menü linki bulunamadı")

        # ── ADIM 1.3: Maps Menü butonundan fotoğraf tara ──
        if result["mekan_adi"]:
            _log.info(f"[1.3] BAŞLIYOR — Maps menü fotoğrafları taranıyor: {result['mekan_adi']}")
            try:
                # 1.1'deki oturum (cookie) korunarak aynı page kullanılıyor
                _log.info("[1.3] Adım 1.1 browser oturumu (cookie) yeniden kullanılıyor — Maps'e gidiliyor...")
                await mapsPage.goto(url, timeout=20000, wait_until="domcontentloaded")
                await mapsPage.wait_for_timeout(3000)
                photoMenus = await extractMenuFromPhotos(mapsPage, result["mekan_adi"], entryId)
                if photoMenus:
                    result["menu_linkleri"] = photoMenus
                    result["menu_linki"] = photoMenus[0]
                    result["menu_kaynak"] = "maps_photo"
                    _log.info(f"[1.3] BASARILI — {len(photoMenus)} menü fotoğrafı bulundu")
                else:
                    _log.info("[1.3] BASARISIZ — menü fotoğrafı bulunamadı")
            except Exception as e:
                _log.error(f"[1.3] BASARISIZ — hata: {e}", exc_info=True)
        else:
            _log.info("[1.3] ATLANDI — mekan adı bilgisi yok")

    finally:
        if cleanup:
            await cleanup()

    _log.info("PIPELINE TAMAMLANDI — menü linki veya fotoğraf bulunamadı")
    return result


# ── SYNC WRAPPER ─────────────────────────────────────────────────────────────

def getMenuDataSync(url: str, entryId: str = "") -> dict:
    """
    Sync wrapper — ThreadPoolExecutor veya doğrudan çağrı için.

    Args:
        url: Google Maps URL
        entryId: Mekan ID'si

    Returns:
        Pipeline sonuç dict'i
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_runGoogleMapsPipeline(url, entryId))
    except Exception as e:
        _log.error(f"Sync wrapper hatası: {e}", exc_info=True)
        return {
            "url": url,
            "mekan_adi": None,
            "adres": None,
            "web_sitesi": None,
            "menu_linki": None,
            "menu_linkleri": None,
            "menu_kaynak": None,
            "hata_sebebi": f"Teknik hata: {str(e)[:150]}",
        }
    finally:
        loop.close()


# ── TOPLU SCRAPE ─────────────────────────────────────────────────────────────

async def _bulkMapsScrape(urls: list, onComplete, poolSize: int, idMap: dict) -> None:
    """
    Paralel sekme havuzu ile toplu Maps menü arama.
    Profil varsa profil ile, yoksa anonim Chrome başlatır.
    """
    chromeProfile = os.path.abspath(CHROME_PROFILE_DIR)
    isProfileExists = os.path.exists(chromeProfile)

    _ARGS = COMMON_LAUNCH_ARGS.copy()
    _CTX_KW = dict(
        viewport={"width": 1440, "height": 900},
        locale="tr-TR",
        timezone_id="Europe/Istanbul",
        extra_http_headers={"Accept-Language": "tr-TR,tr;q=0.9"},
    )

    async with async_playwright() as p:
        if isProfileExists:
            try:
                ctx = await p.chromium.launch_persistent_context(
                    user_data_dir=chromeProfile, channel="chrome",
                    headless=True, args=_ARGS,
                    ignore_default_args=["--enable-automation"], **_CTX_KW,
                )
            except Exception:
                ctx = await p.chromium.launch_persistent_context(
                    user_data_dir=chromeProfile, headless=True, args=_ARGS,
                    ignore_default_args=["--enable-automation"], **_CTX_KW,
                )
            await ctx.add_init_script(_STEALTH_INIT_SCRIPT)

            pool: asyncio.Queue = asyncio.Queue()
            for _ in range(poolSize):
                await pool.put(await ctx.new_page())

            async def processOneUrl(targetUrl: str) -> None:
                page = await pool.get()
                t0 = time.perf_counter()
                entryId = idMap.get(targetUrl, "")
                try:
                    mapsData = await _extractMapsData(page, targetUrl, "bulk-profil")
                    mapsData["url"] = targetUrl
                    if mapsData.get("menu_linki"):
                        mapsData["menu_kaynak"] = "maps"
                    else:
                        # Adım 1.3: fotoğraf tarama
                        if mapsData.get("mekan_adi"):
                            await page.goto(targetUrl, timeout=20000, wait_until="domcontentloaded")
                            await page.wait_for_timeout(3000)
                            photoMenus = await extractMenuFromPhotos(page, mapsData["mekan_adi"], entryId)
                            if photoMenus:
                                mapsData["menu_linkleri"] = photoMenus
                                mapsData["menu_linki"] = photoMenus[0]
                                mapsData["menu_kaynak"] = "maps_photo"
                        if not mapsData.get("menu_linki"):
                            mapsData.setdefault("hata_sebebi", "Hiçbir aşamada menü bulunamadı")
                except Exception as e:
                    _log.error(f"[BulkMaps] TEKNİK HATA {targetUrl}: {e}", exc_info=True)
                    mapsData = {
                        "url": targetUrl, "mekan_adi": None,
                        "menu_linki": None, "menu_kaynak": None,
                        "hata_sebebi": f"Teknik hata: {str(e)[:100]}",
                    }
                finally:
                    await pool.put(page)
                if onComplete:
                    onComplete(targetUrl, mapsData, time.perf_counter() - t0)

            await asyncio.gather(*[processOneUrl(u) for u in urls])
            await ctx.close()

        else:
            try:
                browser = await p.chromium.launch(channel="chrome", headless=True, args=_ARGS)
            except Exception:
                browser = await p.chromium.launch(headless=True, args=_ARGS)

            pool: asyncio.Queue = asyncio.Queue()
            anonContexts = []

            async def _makeWarmedPage():
                anonCtx = await browser.new_context(**_CONTEXT_KWARGS)
                await anonCtx.add_init_script(_STEALTH_INIT_SCRIPT)
                pg = await anonCtx.new_page()
                await _warmUpGoogleSession(pg)
                anonContexts.append(anonCtx)
                return pg

            warmPages = await asyncio.gather(*[_makeWarmedPage() for _ in range(poolSize)])
            for wp in warmPages:
                await pool.put(wp)

            async def processOneUrlAnon(targetUrl: str) -> None:
                page = await pool.get()
                t0 = time.perf_counter()
                entryId = idMap.get(targetUrl, "")
                try:
                    mapsData = await _extractMapsData(page, targetUrl, "bulk-anon")
                    mapsData["url"] = targetUrl
                    if mapsData.get("menu_linki"):
                        mapsData["menu_kaynak"] = "maps"
                    else:
                        if mapsData.get("mekan_adi"):
                            await page.goto(targetUrl, timeout=20000, wait_until="domcontentloaded")
                            await page.wait_for_timeout(3000)
                            photoMenus = await extractMenuFromPhotos(page, mapsData["mekan_adi"], entryId)
                            if photoMenus:
                                mapsData["menu_linkleri"] = photoMenus
                                mapsData["menu_linki"] = photoMenus[0]
                                mapsData["menu_kaynak"] = "maps_photo"
                        if not mapsData.get("menu_linki"):
                            mapsData.setdefault("hata_sebebi", "Hiçbir aşamada menü bulunamadı")
                except Exception as e:
                    _log.error(f"[BulkMaps Anon] TEKNİK HATA {targetUrl}: {e}", exc_info=True)
                    mapsData = {
                        "url": targetUrl, "mekan_adi": None,
                        "menu_linki": None, "menu_kaynak": None,
                        "hata_sebebi": f"Teknik hata: {str(e)[:100]}",
                    }
                finally:
                    await pool.put(page)
                if onComplete:
                    onComplete(targetUrl, mapsData, time.perf_counter() - t0)

            await asyncio.gather(*[processOneUrlAnon(u) for u in urls])
            for c in anonContexts:
                await c.close()
            await browser.close()


def getBulkMenuDataSync(urls: list, onComplete=None, idMap: dict = None) -> None:
    """
    Toplu Maps menü arama — tek Chrome context, paralel sekmeler.
    Her URL tamamlandığında onComplete(url, data, duration) çağrılır.

    Args:
        urls: Google Maps URL listesi
        onComplete: Callback fonksiyonu (url, data, duration)
        idMap: URL -> ID mapping (fotoğraf dosya adları için: id_tamurl)
    """
    idMap = idMap or {}
    chromeProfile = os.path.abspath(CHROME_PROFILE_DIR)
    isProfileExists = os.path.exists(chromeProfile)
    POOL_SIZE = 8

    if isProfileExists:
        _log.info(f"[BulkMaps] Profil kilidi bekleniyor — {len(urls)} URL, {POOL_SIZE} sekme")
        with _PROFILE_LOCK:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_bulkMapsScrape(urls, onComplete, POOL_SIZE, idMap))
            except Exception as e:
                _log.error(f"[BulkMaps] Profil hatası: {e}", exc_info=True)
            finally:
                loop.close()
    else:
        _log.info(f"[BulkMaps] Profil yok — anonim mod, {POOL_SIZE} sekme")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_bulkMapsScrape(urls, onComplete, POOL_SIZE, idMap))
        finally:
            loop.close()
