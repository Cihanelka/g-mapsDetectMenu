"""
Google Maps Menü Linki Çekici — Adım 1.1 DOM Aşaması
Created by: Mapin Data
Created at: 2026-04-21
Subject: Google Maps sayfasından menü linkini bulan fonksiyonlar.
         get_all_menu_links: Sayfadaki TÜM menü linklerini döner.
         get_menu_link: Geriye uyumluluk için ilk menü linkini döner.
"""

import asyncio
from urllib.parse import urlparse, parse_qs, unquote

import aiohttp

from src.utils.logger import get_logger

_log = get_logger("MenuLinkExtractor")


# ── MENÜ LİNKİ ──────────────────────────────────────────────────────────────

async def _verifyLinkAccessible(url: str, timeout: int = 6) -> bool:
    """
    URL'nin erişilebilir olup olmadığını kontrol eder.
    HTTP HEAD isteği atar, 200 OK veya yönlendirme dönerse True, aksi halde False.
    404 dışındaki hataları geçici olarak kabul eder (bazı siteler HEAD'i desteklemez).
    """
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        ) as session:
            async with session.head(url, allow_redirects=True) as response:
                if response.status == 200:
                    return True
                elif response.status in (301, 302, 307, 308):
                    return True
                elif response.status in (403, 405, 429, 500, 502, 503):
                    # Bazı siteler HEAD isteğini desteklemez, GET ile tekrar dene
                    try:
                        async with session.get(url, allow_redirects=True) as get_response:
                            if get_response.status == 200:
                                return True
                    except Exception:
                        pass
                    _log.debug(f"Link erişilebilir değil (status={response.status}): {url}")
                    return False
                else:
                    _log.debug(f"Link erişilebilir değil (status={response.status}): {url}")
                    return False
    except Exception as e:
        _log.debug(f"Link kontrolü başarısız: {url} — {e}")
        return False


def _resolveMenuHref(href: str) -> str | None:
    """
    Google Maps, menü linklerini kendi redirect URL'si üzerinden geçirir.
    Bu fonksiyon redirect URL'sinden gerçek hedefi çıkarır;
    normal URL'leri olduğu gibi döndürür.
    Google Maps haritası / arama sayfası URL'lerini reddeder.
    """
    if not href:
        return None

    # l.instagram.com — Instagram'ın link izleme servisi
    if "l.instagram.com" in href:
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            if "u" in qs:
                real = unquote(qs["u"][0])
                _log.debug(f"l.instagram.com redirect çözüldü: {href} → {real}")
                return real
        except Exception:
            pass
        return href

    # Google servislerini ayırt et
    _GOOGLE_PASS_HOSTS = ("drive.google.com", "docs.google.com", "forms.google.com", "sites.google.com")
    if "google.com" in href:
        if any(host in href for host in _GOOGLE_PASS_HOSTS):
            return href
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            if "url" in qs:
                return unquote(qs["url"][0])
        except Exception:
            pass
        return None
    if "maps.app" in href:
        return None
    return href


async def get_menu_link(page) -> str | None:
    """
    Google Maps sayfasından menü linkini çeker.
    Geriye uyumluluk için ilk menü linkini döner.
    Tüm menüler için get_all_menu_links() kullanın.
    """
    allMenus = await get_all_menu_links(page)
    if allMenus:
        return allMenus[0]
    return None


async def get_all_menu_links(page) -> list[str]:
    """
    Google Maps sayfasındaki TÜM menü linklerini çeker.
    Sayfada birden fazla "View menu" butonu varsa hepsini bulur.
    """
    try:
        candidates = await page.evaluate("""() => {
            const SKIP_HOSTS = new Set([
                'google.com', 'support.google.com', 'maps.google.com',
                'maps.app.goo.gl', 'goo.gl',
            ]);
            const PASS_GOOGLE_HOSTS = new Set([
                'drive.google.com', 'docs.google.com',
                'forms.google.com', 'sites.google.com',
            ]);

            function skipHost(href) {
                try {
                    const host = new URL(href).hostname.replace(/^www\\./, '');
                    if (PASS_GOOGLE_HOSTS.has(host)) return false;
                    return SKIP_HOSTS.has(host) || host.endsWith('.google.com');
                } catch(e) { return true; }
            }

            function findHrefInAncestors(el, maxDepth) {
                let cur = el;
                for (let i = 0; i < maxDepth; i++) {
                    if (!cur) break;
                    const a = cur.tagName === 'A' && cur.href ? cur : cur.querySelector('a[href]');
                    if (a && a.href && !skipHost(a.href)) return a.getAttribute('href');
                    cur = cur.parentElement;
                }
                return null;
            }

            const results = [];

            // ── Strateji A: "Menü" yazan rogA2c div'inin container'ındaki link ──
            document.querySelectorAll('div.rogA2c').forEach(row => {
                const textEl = row.querySelector('.Io6YTe, .fontBodyMedium');
                if (!textEl) return;
                const text = (textEl.textContent || '').trim().toLowerCase();
                if (text !== 'menü' && text !== 'menu') return;
                const href = findHrefInAncestors(row, 8);
                if (href) results.push({ href, score: 120, source: 'rogA2c-metin' });
            });

            // ── Strateji B: data-item-id="menu" container'ındaki tüm <a> ──
            document.querySelectorAll('[data-item-id^="menu"] a[href]').forEach(a => {
                const href = a.getAttribute('href');
                if (href && !skipHost(href)) results.push({ href, score: 100, source: 'data-item-id' });
            });

            // ── Strateji C: aria-label ile menü linki ──
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href || href.startsWith('/') || href.startsWith('#')) return;
                if (skipHost(href)) return;
                const ariaLabel = (a.getAttribute('aria-label') || '').toLowerCase();
                if (ariaLabel.includes('menü') || ariaLabel.includes('menu') ||
                    ariaLabel.includes('view menu') || ariaLabel.includes('menüyü görüntüle')) {
                    results.push({ href, score: 100, source: 'aria-label' });
                }
            });

            const seen = new Set();
            const unique = results.filter(r => {
                if (seen.has(r.href)) return false;
                seen.add(r.href);
                return true;
            });
            unique.sort((a, b) => b.score - a.score);
            return unique;
        }""")

        menuCandidates = [c for c in candidates if c["score"] > 0]
        _log.info(f"Bulunan menü adayı sayısı: {len(menuCandidates)}")

        resolvedCandidates = [
            (candidate, resolved)
            for candidate in menuCandidates
            if (resolved := _resolveMenuHref(candidate["href"]))
        ]

        # HTTP doğrulamalarını sıralı yerine paralel çalıştırıyoruz — birden
        # fazla aday olduğunda her biri için ayrı ayrı 6-15s beklemek, toplam
        # sorgu süresini büyük ölçüde şişiriyordu.
        accessibilityResults = await asyncio.gather(
            *[_verifyLinkAccessible(resolved) for _, resolved in resolvedCandidates]
        )

        validMenus = []
        for (candidate, resolved), isAccessible in zip(resolvedCandidates, accessibilityResults):
            if isAccessible:
                _log.info(f"Menü linki doğrulandı (score={candidate['score']}): {resolved}")
                validMenus.append(resolved)
            else:
                _log.warning(f"Menü linki erişilebilir değil (atlanıyor): {resolved}")

        if not validMenus:
            _log.warning(f"Erişilebilir menü bulunamadı — adaylar: {[c['href'] for c in menuCandidates]}")
        else:
            _log.info(f"Toplam {len(validMenus)} erişilebilir menü linki bulundu")

        return validMenus

    except Exception as e:
        _log.error(f"get_all_menu_links hatası: {e}", exc_info=True)

    return []
