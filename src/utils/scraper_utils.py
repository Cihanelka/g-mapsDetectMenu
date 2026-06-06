"""
Genel yardımcı fonksiyonlar
Created by: Mapin Data
Created at: 2026-04-21
Subject: URL temizleme, metin temizleme, güvenli Playwright erişim sarmalayıcıları
         ve cookie popup kapatıcı.
"""

import re
from urllib.parse import urlparse, parse_qs, unquote


def normalizeGoogleRedirectUrl(url: str | None) -> str | None:
    """Google /url?q= redirect'lerini gerçek URL'ye çevirir."""
    if not url:
        return None
    if "google." in url and "/url?" in url:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        realUrl = qs.get("q", [None])[0]
        if realUrl:
            return unquote(realUrl)
    return url


def cleanText(value: str | None) -> str | None:
    """Boşluk karakterlerini, ikon satırlarını ve gereksiz whitespace'i temizler."""
    if not value:
        return None
    value = value.replace("\u200b", " ").replace("\xa0", " ").strip()
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    cleanedLines = [line for line in lines if not (len(line) == 1 and not line.isalnum())]
    return " ".join(cleanedLines).strip() if cleanedLines else None


async def safeText(locator) -> str | None:
    """Locator görünürse inner_text döndürür, hata olursa None."""
    try:
        if await locator.count() > 0 and await locator.first.is_visible():
            return cleanText(await locator.first.inner_text())
    except Exception:
        pass
    return None


async def safeAttr(locator, attr: str) -> str | None:
    """Locator varsa istenen attribute'u döndürür, hata olursa None."""
    try:
        if await locator.count() > 0:
            val = await locator.first.get_attribute(attr)
            return cleanText(val) if val else None
    except Exception:
        pass
    return None


async def safeHref(locator) -> str | None:
    """href attribute'unu alır, Google redirect varsa gerçek URL'ye çevirir."""
    try:
        if await locator.count() > 0:
            href = await locator.first.get_attribute("href")
            return normalizeGoogleRedirectUrl(href)
    except Exception:
        pass
    return None


async def clickCookieIfAny(page) -> None:
    """Sayfada cookie/consent popup varsa kapatır."""
    candidates = [
        page.get_by_role("button", name=re.compile(r"Kabul et|Accept all", re.I)),
        page.get_by_role("button", name=re.compile(r"Tümünü reddet|Reject all", re.I)),
    ]
    for btn in candidates:
        try:
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click(timeout=2000)
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue
