"""
Browser Sabitleri — Playwright Chrome profil kilidi, stealth script ve context ayarları.
Created by: Mapin Data
Created at: 2026-04-21
Subject: Tüm scraping fonksiyonları tarafından paylaşılan Chrome yapılandırması.
         Profil kilidi, aynı anda tek Chrome instance'ı kullanılmasını garanti eder.
"""

import threading

# Chrome profili tek seferde yalnızca bir instance tarafından kullanılabilir.
# Bu kilit toplu sorguların profil üzerinde çakışmasını önler.
_PROFILE_LOCK = threading.Lock()

# navigator.webdriver ve diğer bot imzalarını silen JS
_STEALTH_INIT_SCRIPT = """
() => {
    // webdriver özelliğini sil
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
    });

    // chrome runtime nesnesini ekle (headless'ta eksik olur)
    if (!window.chrome) {
        window.chrome = { runtime: {} };
    }

    // plugins dizisini gerçekmiş gibi göster
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
        configurable: true,
    });

    // languages alanını doldur
    Object.defineProperty(navigator, 'languages', {
        get: () => ['tr-TR', 'tr', 'en-US', 'en'],
        configurable: true,
    });

    // permissions API'ını geçici olarak patch'le
    const originalQuery = window.navigator.permissions?.query;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) =>
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters);
    }

    // CDP Runtime.enable tespitini engelle
    const _open = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        return _open.call(this, method, url, ...rest);
    };
}
"""

_CONTEXT_KWARGS = dict(
    viewport={"width": 1440, "height": 900},
    locale="tr-TR",
    timezone_id="Europe/Istanbul",
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    extra_http_headers={
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    java_script_enabled=True,
    bypass_csp=False,
)

# Ortak Chrome başlatma argümanları
COMMON_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--no-first-run",
    "--mute-audio",
    "--disable-sync",
    "--disable-notifications",
    "--disable-session-crashed-bubble",
    "--disable-default-apps",
    "--window-size=1440,900",
]
