"""
Subject: Chrome scraper profilini bir kerelik oluşturur ve Google cookie'lerini ısıtır.
Created by: Mapin Data
"""

import argparse
import asyncio
import os
import random
import shutil
import sys

from playwright.async_api import async_playwright

from config.settings import CHROME_PROFILE_DIR
from src.scraper.browser_config import PERSISTENT_CONTEXT_KWARGS, _STEALTH_INIT_SCRIPT
from src.utils.scraper_utils import clickCookieIfAny
from src.utils.logger import setup_logging

_log = setup_logging()

_MAPS_VERIFY_URL = "https://maps.app.goo.gl/ysvYHEDGBWNqwGc39"


async def _read_maps_tabs(page) -> list[str]:
    """Maps sayfasındaki sekme etiketlerini döndürür."""
    return await page.evaluate(
        """() => Array.from(document.querySelectorAll('[role="tab"]'))
            .map((tab) => (tab.innerText || '').trim())
            .filter(Boolean)"""
    )


async def setup_chrome_profile(reset: bool = False) -> None:
    """Kalıcı Chrome profilini oluşturur, cookie ısınması yapar ve Maps sekmelerini doğrular."""
    profile_path = os.path.abspath(CHROME_PROFILE_DIR)

    if reset and os.path.exists(profile_path):
        shutil.rmtree(profile_path)
        _log.info(f"Mevcut profil silindi: {profile_path}")

    os.makedirs(profile_path, exist_ok=True)
    _log.info(f"Profil klasörü hazır: {profile_path}")

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            **PERSISTENT_CONTEXT_KWARGS,
        )

        await context.add_init_script(_STEALTH_INIT_SCRIPT)
        page = await context.new_page()

        _log.info("Google ana sayfasına gidiliyor (cookie ısınması)...")
        await page.goto("https://www.google.com", timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(random.randint(1500, 2500))
        await clickCookieIfAny(page)
        await page.wait_for_timeout(random.randint(800, 1200))

        _log.info("Maps arayüzü doğrulanıyor...")
        await page.goto(_MAPS_VERIFY_URL, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(8000)
        maps_tabs = await _read_maps_tabs(page)
        _log.info(f"Maps sekmeleri: {maps_tabs}")

        cookies = await context.cookies()
        google_cookies = [cookie for cookie in cookies if "google" in cookie.get("domain", "")]
        _log.info(f"Toplam cookie: {len(cookies)}, Google cookie: {len(google_cookies)}")

        has_menu_tab = any("menü" in tab.lower() or "menu" in tab.lower() for tab in maps_tabs)
        if not has_menu_tab:
            _log.warning(
                "Menü sekmesi doğrulanamadı — profil kısıtlı Maps arayüzü ile oluşmuş olabilir. "
                "python setup_session.py --reset ile yeniden oluşturun."
            )
        else:
            _log.info("Menü sekmesi doğrulandı — profil kullanıma hazır.")

        await context.close()

    _log.info("chrome_scraper_profile başarıyla oluşturuldu ve ısıtıldı.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    parser = argparse.ArgumentParser(description="Chrome scraper profilini oluşturur.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Mevcut chrome_scraper_profile klasörünü silip sıfırdan oluşturur.",
    )
    args = parser.parse_args()
    asyncio.run(setup_chrome_profile(reset=args.reset))
