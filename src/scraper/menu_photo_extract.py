"""
Menü Fotoğraf Extractor — Adım 1.3: Google Maps Menü Butonu ve Fotoğraf Tarama.
Created by: Mapin Data
Created at: 2026-04-21
Subject: Maps'teki Menü butonuna tıklayarak açılan fotoğrafları gezme,
         XHR yanıtlarını intercept etme ve belirlenen tarihten sonraki menüleri bulma.
         Minimum tarih: Haziran 2024.
         Menü sekmesi bulunamazsa mekanın genel fotoğraflarına (kapak resmi) düşer.
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
from playwright.async_api import Page, Response

from src.utils.logger import get_logger

_log = get_logger("MenuPhotoExtract")

_IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "images"

# Minimum kabul edilebilir tarih: Haziran 2024 (daha gevşetilmiş)
_MIN_MENU_DATE = datetime(2024, 6, 1)


def _sanitizeUrlToFilename(url: str, photoId: str = "") -> str:
    """
    URL'yi dosya adı olarak kullanılabilir hale getirir.
    Format: id_tamurl (örn: 123_https___example_com_menu.jpg)
    Geçersiz karakterleri '_' ile değiştirir.
    """
    name = url.replace("https://", "").replace("http://", "")
    name = re.sub(r'[\\/:*?"<>|\s]', '_', name)
    if len(name) > 150:
        name = name[:150]
    if photoId:
        name = f"{photoId}_{name}"
    return name + ".jpg"


async def _downloadPhotoToImages(url: str, photoId: str = "") -> Optional[str]:
    """
    Fotoğrafı indirir ve images/ klasörüne kaydeder.
    Dosya adı formatı: id_tamurl
    Returns: kaydedilen dosya yolu veya None
    """
    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitizeUrlToFilename(url, photoId)
    savePath = _IMAGES_DIR / filename

    if savePath.exists():
        _log.debug(f"[1.3] Zaten mevcut, atlanıyor: {filename}")
        return str(savePath)

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.google.com/maps/",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    savePath.write_bytes(content)
                    _log.info(f"[1.3] Görsel kaydedildi: {filename} ({len(content) // 1024} KB)")
                    return str(savePath)
                else:
                    _log.warning(f"[1.3] İndirme HTTP {resp.status}: {url[:80]}")
                    return None
    except Exception as e:
        _log.warning(f"[1.3] İndirme hatası: {e}")
        return None


def _parsePhotoDate(dateStr: str) -> Optional[datetime]:
    """
    Fotoğraf tarih string'ini datetime'a çevir.
    Çeşitli formatları destekler: 2025-06-15, Haziran 2025, Jun 2025, vb.
    """
    if not dateStr:
        return None

    dateStr = dateStr.strip().lower()

    trMonths = {
        'ocak': 1, 'subat': 2, 'mart': 3, 'nisan': 4, 'mayis': 5, 'haziran': 6,
        'temmuz': 7, 'agustos': 8, 'eylul': 9, 'ekim': 10, 'kasim': 11, 'aralik': 12
    }

    enMonths = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }

    months = {**trMonths, **enMonths}

    try:
        isoMatch = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', dateStr)
        if isoMatch:
            year, month, day = map(int, isoMatch.groups())
            return datetime(year, month, day)

        monthYearMatch = re.match(r'(\w+)\s+(\d{4})', dateStr)
        if monthYearMatch:
            monthName, year = monthYearMatch.groups()
            month = months.get(monthName.lower())
            if month:
                return datetime(int(year), month, 1)

        fullDateMatch = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', dateStr)
        if fullDateMatch:
            day, monthName, year = fullDateMatch.groups()
            month = months.get(monthName.lower())
            if month:
                return datetime(int(year), month, int(day))

    except (ValueError, AttributeError) as e:
        _log.debug(f"Tarih parse hatası '{dateStr}': {e}")

    return None


def _findLh3Urls(obj, found: list) -> None:
    """
    Herhangi derinlikte iç içe list/dict yapısını rekürsif gezarak
    lh3.googleusercontent.com içeren tüm string'leri toplar.
    Protocol-relative (//lh3.) veya https:// ile başlayanlar dahil.
    JSON escape karakterlerini (backslash-slash) düzgün şekilde işler.
    """
    if isinstance(obj, str):
        if 'lh3.googleusercontent.com' in obj:
            url = obj.strip()
            url = url.replace('\\/', '/').replace('\\', '')
            if url.startswith('//'):
                url = 'https:' + url
            elif not url.startswith('https://'):
                url = 'https://' + url
            found.append(url)
    elif isinstance(obj, list):
        for item in obj:
            _findLh3Urls(item, found)
    elif isinstance(obj, dict):
        for v in obj.values():
            _findLh3Urls(v, found)


def _findDateArrays(obj, found: list, depth: int = 0) -> None:
    """
    Rekürsif olarak [yıl, ay, gün] veya [yıl, ay, gün, saat] şeklindeki
    tarih array'lerini arar. Örnek: [2025, 4, 1] veya [2025, 4, 1, 18].
    """
    if depth > 15:
        return
    if isinstance(obj, list):
        if (3 <= len(obj) <= 4
                and all(isinstance(x, int) for x in obj[:3])
                and 2000 <= obj[0] <= 2100
                and 1 <= obj[1] <= 12
                and 1 <= obj[2] <= 31):
            found.append(obj)
        else:
            for item in obj:
                _findDateArrays(item, found, depth + 1)
    elif isinstance(obj, dict):
        for v in obj.values():
            _findDateArrays(v, found, depth + 1)


# Ham text'te lh3 URL'sine yakın [YYYY,MM,DD] dizisini arayan regex
_DATE_ARRAY_REGEX = re.compile(r'\[(2\d{3}),\s*(\d{1,2}),\s*(\d{1,2})(?:,\s*\d+)?\]')


def _findDateNearUrl(rawText: str, photoUrl: str) -> Optional[datetime]:
    """
    Ham XHR text'inde fotoğraf URL'sine pozisyon olarak en yakın
    [YYYY, MM, DD] tarih array'ini bulur.
    Google Maps XHR yapısında fotoğraf ve tarihi genellikle aynı nested
    array içinde yer alır — proximity ile doğru tarih seçilir.
    """
    # URL'nin rawText içindeki pozisyonunu bul
    urlPos = rawText.find(photoUrl[:60])  # İlk 60 karakter yeterli
    if urlPos == -1:
        # Kısaltılmış URL'yi de dene
        shortUrl = photoUrl.split('?')[0][:60]
        urlPos = rawText.find(shortUrl)
    if urlPos == -1:
        return None

    bestDate: Optional[datetime] = None
    bestDistance = float('inf')

    for m in _DATE_ARRAY_REGEX.finditer(rawText):
        try:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            distance = abs(m.start() - urlPos)
            if distance < bestDistance:
                bestDistance = distance
                bestDate = datetime(year, month, day)
        except ValueError:
            continue

    return bestDate


def _stripXhrPrefix(text: str) -> str:
    """
    Google XHR yanıtlarının başındaki ')]}\'' ve benzeri XSSI önleme
    prefix'lerini temizler.
    """
    text = text.strip()
    for prefix in (")]}'\n", ")]}\'\n", ")]}", ")]}'" , "/*O_o*/"):
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    stripped = re.sub(r'^[\)\]\}\'\s]+', '', text, count=1)
    return stripped if stripped != text else text


# Ham response text'inden lh3 URL'lerini çıkaran regex
_LH3_URL_REGEX = re.compile(
    r'"(https?:\\?/\\?/[^"]*lh3\.googleusercontent\.com[^"]*)"',
)


def _extractPhotoUrlFromXhr(rawData, rawText: str = "") -> Optional[tuple[str, datetime]]:
    """
    XHR yanıtından fotoğraf URL'si ve tarihini çıkar.
    Gerçek Maps XHR formatı: iç içe list yapısı, lh3 URL'leri derin konumda,
    tarih [yıl, ay, gün] array olarak geliyor.

    Args:
        rawData: JSON parse edilmiş veri (list veya dict)
        rawText: Ham response text — regex ile tam URL çıkarmak için

    Returns:
        Tuple: (photo_url, date) veya None
    """
    try:
        lh3Urls: list[str] = []
        if rawText:
            regexMatches = _LH3_URL_REGEX.findall(rawText)
            for match in regexMatches:
                unescaped = match.replace('\\/', '/').replace('\\', '')
                lh3Urls.append(unescaped)
                _log.debug(f"[1.3] Regex ile URL bulundu ({len(unescaped)} karakter): {unescaped[:80]}...")

        jsonUrls: list[str] = []
        _findLh3Urls(rawData, jsonUrls)
        for u in jsonUrls:
            normalized = u.replace('\\/', '/').replace('\\', '')
            if normalized not in lh3Urls:
                lh3Urls.append(normalized)

        if not lh3Urls:
            return None

        _log.debug(f"[1.3] XHR'den {len(lh3Urls)} lh3 URL bulundu — uzunluklar: {[len(u) for u in lh3Urls]}")

        gpmsCandidates = [u for u in lh3Urls if 'gpms-cs-s' in u or 'googleusercontent.com/gpms' in u]
        if gpmsCandidates:
            photoUrl = max(gpmsCandidates, key=len)
        else:
            photoUrl = max(lh3Urls, key=len)
        _log.debug(f"[1.3] Seçilen URL ({len(photoUrl)} karakter): {photoUrl}")

        # Önce URL'ye pozisyon olarak en yakın tarihi dene (daha isabetli)
        photoDate: Optional[datetime] = None
        if rawText:
            photoDate = _findDateNearUrl(rawText, photoUrl)

        # Proximity ile bulunamazsa eski yöntem: tüm tarih array'lerinden en geç olanı
        if photoDate is None:
            dateArrays: list = []
            _findDateArrays(rawData, dateArrays)
            if dateArrays:
                latestArr = max(dateArrays, key=lambda a: (a[0], a[1], a[2]))
                try:
                    photoDate = datetime(latestArr[0], latestArr[1], latestArr[2])
                except ValueError:
                    pass

        if photoUrl and photoDate:
            return photoUrl, photoDate

        if photoUrl:
            _log.debug("[1.3] XHR'de tarih bulunamadı — bugünün tarihi kullanılıyor")
            return photoUrl, datetime.now()

    except (IndexError, TypeError, AttributeError) as e:
        _log.debug(f"XHR parse hatası: {e}")

    return None


_NEXT_PHOTO_BUTTON_SELECTORS = [
    'button[aria-label*="next" i]',
    'button[aria-label*="sonraki" i]',
    'button[aria-label*="ileri" i]',
    'div[role="button"][aria-label*="next" i]',
    'button[jsaction*="next"]',
]

_COVER_PHOTO_SELECTORS = [
    'button.aoRNLd',
    'button[jsaction*="heroHeaderImage"]',
    'div.RZ66Rb button',
    'div.ZKCDEc img',
    'button.OaVZ6',
    'button[aria-label*="Fotoğraf" i]',
    'button[aria-label*="Photo" i]',
    'img.aoRNLd',
    'button[data-photo-index="0"]',
]


async def _clickCoverPhoto(page: Page) -> bool:
    """
    Mekanın kapak (kapak resmi/header) fotoğrafına tıklayarak genel fotoğraf
    galerisini/görüntüleyicisini açar. Menü sekmesi bulunamadığında fallback
    olarak kullanılır — Adım 1.3'ün "Menü tab'ı bulunamazsa mekanın
    fotoğraflarında gezilecek" gereksinimi.

    Returns:
        Tıklama başarılıysa True, kapak fotoğrafı bulunamazsa False.
    """
    for selector in _COVER_PHOTO_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0 and await locator.is_visible():
                await locator.click()
                _log.info(f"[1.3] Kapak fotoğrafına tıklandı (selector: {selector})")
                return True
        except Exception:
            continue

    _log.warning("[1.3] Kapak fotoğrafı bulunamadı — hiçbir selector eşleşmedi")
    return False


_MAX_COVER_PHOTOS_TO_BROWSE = 15
_MAX_GRID_PHOTOS_TO_BROWSE = 15
_MAX_CONSECUTIVE_EMPTY_CLICKS = 4


async def _browseCoverPhotosWithNextButton(page: Page, photoResults: list) -> None:
    """
    Kapak fotoğrafı tıklandığında açılan tam ekran görüntüleyicide "sonraki"
    butonuna art arda basarak mekanın fotoğraflarını dolaşır. XHR intercept
    handler'ı zaten çağıran fonksiyon tarafından kaydedilmiş olduğundan,
    burada sadece gezinme (navigation) yapılır. Art arda yeni fotoğraf
    gelmeyince (aynı fotoğraflar tekrar ediyorsa) erken sonlandırılır.
    """
    consecutiveNoNewResults = 0
    for _ in range(_MAX_COVER_PHOTOS_TO_BROWSE):
        resultCountBefore = len(photoResults)
        clickedNext = False
        for nextSelector in _NEXT_PHOTO_BUTTON_SELECTORS:
            try:
                nextBtn = page.locator(nextSelector).first
                if await nextBtn.count() > 0 and await nextBtn.is_visible():
                    await nextBtn.click()
                    clickedNext = True
                    await page.wait_for_timeout(600)
                    break
            except Exception:
                continue
        if not clickedNext:
            break
        if len(photoResults) > resultCountBefore:
            consecutiveNoNewResults = 0
        else:
            consecutiveNoNewResults += 1
            if consecutiveNoNewResults >= _MAX_CONSECUTIVE_EMPTY_CLICKS:
                break


async def _scrapeMenuPhotosFromMaps(page: Page, mekanAdi: str, entryId: str = "") -> Optional[list[dict]]:
    """
    Google Maps sayfasındaki Menü butonuna tıklayarak fotoğrafları gezer.

    Args:
        page: Playwright Page instance (zaten Maps sayfasında olmalı)
        mekanAdi: Mekanın adı (log için)
        entryId: Mekan ID'si (dosya adı için: id_tamurl)

    Returns:
        Liste: [{"url": str, "date": datetime, "is_valid": bool}, ...] veya None
    """
    photoResults: list[dict] = []
    interceptedUrls: set[str] = set()
    handlerRef: list = [None]

    async def handleResponse(response: Response):
        url = response.url
        if 'v1?' in url and 'authuser' in url:
            try:
                body = await response.body()
                try:
                    text = body.decode('utf-8')
                except UnicodeDecodeError:
                    return

                cleaned = _stripXhrPrefix(text)
                _log.debug(f"[1.3] XHR yanıt uzunluğu: {len(text)} karakter")
                data = None
                try:
                    data = json.loads(cleaned)
                except json.JSONDecodeError:
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        arrayMatch = re.search(r'(\[.*\])', text, re.DOTALL)
                        if arrayMatch:
                            try:
                                data = json.loads(arrayMatch.group(1))
                            except json.JSONDecodeError:
                                return
                        else:
                            return
                if data is None:
                    return

                result = _extractPhotoUrlFromXhr(data, rawText=text)
                if result:
                    photoUrl, photoDate = result
                    if photoUrl not in interceptedUrls:
                        interceptedUrls.add(photoUrl)
                        isValid = photoDate >= _MIN_MENU_DATE
                        _log.debug(f"[1.3] Fotoğraf yakalandı: {photoUrl[:100]}... | Tarih: {photoDate.isoformat()} | Geçerli: {isValid}")
                        photoResults.append({
                            "url": photoUrl,
                            "date": photoDate,
                            "is_valid": isValid,
                        })

            except Exception as e:
                _log.debug(f"[1.3] Response işleme hatası: {e}")

    def responseHandlerWrapper(response):
        asyncio.create_task(handleResponse(response))

    handlerRef[0] = responseHandlerWrapper
    page.on("response", responseHandlerWrapper)

    try:
        # ── Menü butonunu bul ve tıkla ──
        _log.info(f"[1.3] Menü butonu aranıyor: {mekanAdi}")

        menuButton = None
        matchedSelector = None
        hasMenuTab = True
        usingCoverPhotoFallback = False

        try:
            allTabs = await page.evaluate("""() => {
                const tabs = document.querySelectorAll('[role="tab"]');
                return Array.from(tabs).map((t, i) => ({
                    index: i,
                    label: t.getAttribute('aria-label') || '',
                    text: t.innerText || '',
                    selected: t.getAttribute('aria-selected'),
                    tag: t.tagName,
                }));
            }""")
            _log.info(f"[1.3] Sayfadaki tab butonları: {allTabs}")

            hasMenuTab = any(
                'menü' in (t.get('label', '') + ' ' + t.get('text', '')).lower()
                or 'menu' in (t.get('label', '') + ' ' + t.get('text', '')).lower()
                for t in allTabs
            )
            if not hasMenuTab:
                _log.warning(
                    f"[1.3] Bu mekanın Menü sekmesi yok — tab listesi: {[t.get('text') for t in allTabs]} "
                    "— kapak fotoğrafına geçiliyor"
                )
        except Exception:
            pass

        menuTabSelectors = [
            'button[role="tab"][aria-label="Menü"]',
            'button[role="tab"][aria-label="Menu"]',
            '[role="tab"][aria-label="Menü"]',
            '[role="tab"][aria-label="Menu"]',
            'button.hh2c6[aria-label*="Menü" i]',
            'button[role="tab"][aria-label*="Menü" i]',
            'button[role="tab"][aria-label*="Menu" i]',
            '[data-item-id="menu"]',
            'button[data-item-id="menu"]',
            'a[data-item-id="menu"]',
            'button[aria-label*="Menü" i]',
            'button[aria-label*="Menu" i]',
            'div[role="tab"][aria-label*="Menü" i]',
            'div[role="tab"][aria-label*="Menu" i]',
            '*[data-item-id*="menu"]',
            'span:has-text("Menü")',
            'span:has-text("Menu")',
            'button:has-text("Menü")',
            'button:has-text("Menu")',
        ]

        if hasMenuTab:
            for selector in menuTabSelectors:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        menuButton = locator
                        matchedSelector = selector
                        break
                except Exception:
                    continue

            if not menuButton:
                _log.warning(f"[1.3] Menü butonu bulunamadı: {mekanAdi} — kapak fotoğrafına geçiliyor")

        if not menuButton:
            usingCoverPhotoFallback = True
            coverClicked = await _clickCoverPhoto(page)
            if not coverClicked:
                _log.warning(f"[1.3] Kapak fotoğrafı da bulunamadı, mekan fotoğrafları taranamıyor: {mekanAdi}")
                return None
            await page.wait_for_timeout(2000)

        if not usingCoverPhotoFallback:
            try:
                buttonHtml = await menuButton.evaluate("el => el.outerHTML")
                _log.debug(f"[1.3] Menü butonu bulundu [{matchedSelector}]: {buttonHtml[:300]}")
            except Exception:
                _log.debug(f"[1.3] Menü butonu bulundu [{matchedSelector}]")

            await menuButton.click()
            _log.info("[1.3] Menü butonuna tıklandı, panel açılıyor...")
            await page.wait_for_timeout(2500)

        if not usingCoverPhotoFallback:
            try:
                selectedLabel = await page.evaluate("""() => {
                    const sel = document.querySelector('[role="tab"][aria-selected="true"]');
                    return sel ? (sel.getAttribute('aria-label') || sel.innerText || '') : '';
                }""")
                _log.info(f"[1.3] Tıklama sonrası seçili tab: '{selectedLabel}'")
                if 'menü' not in selectedLabel.lower() and 'menu' not in selectedLabel.lower():
                    _log.warning("[1.3] Menü sekmesi aktif değil — JS ile tıklama deneniyor...")
                    clicked = await page.evaluate("""() => {
                        const tabs = document.querySelectorAll('[role="tab"]');
                        for (const tab of tabs) {
                            const label = (tab.getAttribute('aria-label') || tab.innerText || '').toLowerCase();
                            if (label.includes('menü') || label.includes('menu')) {
                                tab.click();
                                return label;
                            }
                        }
                        return null;
                    }""")
                    if clicked:
                        _log.info(f"[1.3] JS ile menü tabına tıklandı: '{clicked}'")
                        await page.wait_for_timeout(2000)
                    else:
                        _log.warning("[1.3] JS ile de menü tabı bulunamadı")
            except Exception as tabErr:
                _log.debug(f"[1.3] Tab doğrulama hatası: {tabErr}")

        try:
            domDebug = await page.evaluate("""() => {
                const imgs = document.querySelectorAll('img[src*="lh3"]');
                const allImgs = document.querySelectorAll('img');
                const tabPanels = document.querySelectorAll('[role="tabpanel"]');
                const selectedTab = document.querySelector('[role="tab"][aria-selected="true"]');
                return {
                    lh3ImgCount: imgs.length,
                    lh3Srcs: Array.from(imgs).slice(0, 5).map(i => i.src.slice(0, 100)),
                    totalImgCount: allImgs.length,
                    tabPanelCount: tabPanels.length,
                    selectedTabLabel: selectedTab ? selectedTab.getAttribute('aria-label') : null,
                    selectedTabText: selectedTab ? selectedTab.innerText : null,
                    pageUrl: location.href.slice(0, 150),
                };
            }""")
            _log.debug(
                f"[1.3] DOM DEBUG: lh3 img={domDebug['lh3ImgCount']}, total img={domDebug['totalImgCount']}, "
                f"tabPanels={domDebug['tabPanelCount']}, selectedTab={domDebug['selectedTabLabel']}/{domDebug['selectedTabText']}, "
                f"url={domDebug['pageUrl']}"
            )
        except Exception as dbgErr:
            _log.debug(f"[1.3] DOM debug hatası: {dbgErr}")

        # ── Fotoğraf galerisini bul ──
        photoContainerSelectors = [
            'button.K4UgGe',
            'button.K4UgGe img.DaSXdd',
            'button[data-carousel-index]',
            'button[jsaction*="carousel.photo"]',
            '.K4UgGe',
            'div.K4UgGe',
            'img.DaSXdd',
            'div[role="dialog"] .K4UgGe',
            'div[role="dialog"] img',
            'div[role="dialog"] div[role="button"] img',
            '[data-testid="menu-photo"]',
            'img[src*="lh3.googleusercontent.com"]',
            '[role="tabpanel"] img',
            'div[data-index]',
        ]

        photos: list = []
        for selector in photoContainerSelectors:
            try:
                locators = page.locator(selector)
                count = await locators.count()
                _log.info(f"[1.3] Selector denendi: {selector} → {count} eşleşme")
                if count > 0:
                    photos = await locators.all()
                    _log.info(f"[1.3] {count} fotoğraf bulundu (selector: {selector})")
                    break
            except Exception as e:
                _log.info(f"[1.3] Selector hatası {selector}: {e}")
                continue

        if not photos:
            if usingCoverPhotoFallback:
                # Kapak fotoğrafına tıklandığında genellikle grid değil, doğrudan
                # tam ekran görüntüleyici açılır — "sonraki" butonuyla gezinerek
                # mekanın fotoğraflarını tek tek dolaşıyoruz.
                _log.info("[1.3] Fotoğraf galerisi (grid) yok — tam ekran görüntüleyicide 'sonraki' ile geziliyor")
                await _browseCoverPhotosWithNextButton(page, photoResults)
            else:
                _log.warning("[1.3] Fotoğraf galerisi bulunamadı — tüm selector'lar denendi")

                try:
                    jsElements = await page.evaluate("""() => {
                        const elements = document.querySelectorAll('.K4UgGe');
                        return Array.from(elements).map((el, i) => ({
                            index: i,
                            tagName: el.tagName,
                            className: el.className,
                            hasImg: el.querySelector('img') !== null,
                            imgSrc: el.querySelector('img')?.src || null,
                            isVisible: el.offsetParent !== null,
                        }));
                    }""")
                    _log.info(f"[1.3] JavaScript ile {len(jsElements)} .K4UgGe elementi bulundu")
                except Exception as jsErr:
                    _log.info(f"[1.3] JavaScript seçim hatası: {jsErr}")

                if not photoResults:
                    return None
        else:
            # ── Her fotoğrafa tıkla ve XHR yanıtlarını topla ──
            # Fazla sayıda fotoğrafta tek tek tıklamak süreyi çok uzatıyordu —
            # üst limitle sınırlandırıp, art arda yeni sonuç gelmeyince erken çıkıyoruz.
            maxPhotos = min(len(photos), _MAX_GRID_PHOTOS_TO_BROWSE)
            _log.debug(f"[1.3] {len(photos)} fotoğraftan {maxPhotos} tanesi taranacak...")

            consecutiveNoNewResults = 0
            for i, photo in enumerate(photos[:maxPhotos]):
                resultCountBefore = len(photoResults)
                try:
                    isVisible = await photo.is_visible()
                    if not isVisible:
                        _log.debug(f"[1.3] Fotoğraf {i+1} görünür değil, atlanıyor")
                        continue

                    _log.debug(f"[1.3] Fotoğraf {i+1}/{maxPhotos} tıklanıyor...")
                    await photo.click()
                    await page.wait_for_timeout(900)

                    for nextSelector in _NEXT_PHOTO_BUTTON_SELECTORS:
                        try:
                            nextBtn = page.locator(nextSelector).first
                            if await nextBtn.count() > 0 and await nextBtn.is_visible():
                                await nextBtn.click()
                                _log.debug("[1.3] Sonraki fotoğrafa geçildi")
                                await page.wait_for_timeout(500)
                                break
                        except Exception:
                            continue

                except Exception as e:
                    _log.debug(f"[1.3] Fotoğraf {i+1} tıklama hatası: {e}")
                    continue
                finally:
                    if len(photoResults) > resultCountBefore:
                        consecutiveNoNewResults = 0
                    else:
                        consecutiveNoNewResults += 1
                        if consecutiveNoNewResults >= _MAX_CONSECUTIVE_EMPTY_CLICKS:
                            _log.debug("[1.3] Art arda yeni fotoğraf gelmedi — tarama erken sonlandırıldı")
                            break

        # ── Sonuçları değerlendir ──
        if not photoResults:
            _log.warning("[1.3] Hiç fotoğraf verisi yakalanamadı")
            return None

        validPhotos = [p for p in photoResults if p["is_valid"]]

        if validPhotos:
            _log.info(f"[1.3] {len(validPhotos)} geçerli menü fotoğrafı bulundu (Haziran 2024+)")
            for photo in validPhotos:
                await _downloadPhotoToImages(photo["url"], entryId)
            validPhotos.sort(key=lambda x: x["date"], reverse=True)
            return validPhotos
        else:
            oldestDate = min(p["date"] for p in photoResults)
            _log.warning(f"[1.3] Tüm fotoğraflar eski (en yeni: {oldestDate.isoformat()})")
            return None

    except Exception as e:
        _log.error(f"[1.3] Menü fotoğraf tarama hatası: {e}", exc_info=True)
        return None
    finally:
        if handlerRef[0]:
            try:
                page.remove_listener("response", handlerRef[0])
            except Exception:
                pass


async def extractMenuFromPhotos(page, mekanAdi: str, entryId: str = "") -> Optional[list[str]]:
    """
    Adım 1.3: Maps Menü butonundan fotoğraf menüsü çıkar.

    Args:
        page: Playwright Page instance
        mekanAdi: Mekanın adı
        entryId: Mekan ID'si (dosya adı için kullanılır: id_tamurl)

    Returns:
        Tüm geçerli menü fotoğraf URL'lerinin listesi (tarihe göre sıralı, en yeni önce) veya None
    """
    results = await _scrapeMenuPhotosFromMaps(page, mekanAdi, entryId)
    if results and len(results) > 0:
        photoUrls = [r["url"] for r in results]
        _log.info(f"[1.3] {len(photoUrls)} menü fotoğrafı bulundu ve indirildi")
        for i, url in enumerate(photoUrls, 1):
            _log.info(f"[1.3] Fotoğraf {i}/{len(photoUrls)}: {url[:80]}...")
        return photoUrls
    return None
