"""
Merkezi Loglama Modülü
Created by: Mapin Data
Created at: 2026-04-21
Subject: Her uygulama başlatıldığında logs/ altındaki info/, error/, warning/
         klasörlerini temizler, yeni oturuma ait log dosyaları oluşturur.
         Terminal çıktısı yalnızca INFO ve ERROR seviyelerini gösterir,
         ANSI renk kodları ile biçimlendirilir.
"""

import logging
import os
import shutil
from datetime import datetime

# ── Renk kodları (ANSI) ─────────────────────────────────────────────────────
_RESET   = "\033[0m"
_BOLD    = "\033[1m"
_CYAN    = "\033[36m"
_GREEN   = "\033[32m"
_YELLOW  = "\033[33m"
_RED     = "\033[31m"
_MAGENTA = "\033[35m"
_DIM     = "\033[2m"

_LEVEL_COLORS = {
    "DEBUG":    _DIM    + "[DEBUG]"   + _RESET,
    "INFO":     _GREEN  + "[INFO] "   + _RESET,
    "WARNING":  _YELLOW + "[WARN] "   + _RESET,
    "ERROR":    _RED    + _BOLD + "[ERROR]"   + _RESET,
    "CRITICAL": _MAGENTA + _BOLD + "[CRIT] " + _RESET,
}

_LOG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs"))
_LOG_SUBDIRS = ("info", "error", "warning")


# ── Renkli terminal formatter ────────────────────────────────────────────────

class _ColorFormatter(logging.Formatter):
    """Terminal çıktısı için renkli formatter — sadece INFO ve ERROR gösterir."""

    _FMT = "{level_tag} {cyan}{time}{reset}  {dim}{name}{reset}  {msg}"

    def format(self, record: logging.LogRecord) -> str:
        level_tag = _LEVEL_COLORS.get(record.levelname, f"[{record.levelname}]")
        time_str  = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        name      = record.name.replace("mapin.", "")

        line = self._FMT.format(
            level_tag = level_tag,
            cyan      = _CYAN,
            time      = time_str,
            reset     = _RESET,
            dim       = _DIM,
            name      = name,
            msg       = record.getMessage(),
        )

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


# ── Sade dosya formatter ─────────────────────────────────────────────────────

class _FileFormatter(logging.Formatter):
    _FMT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    _DATE = "%Y-%m-%d %H:%M:%S"

    def __init__(self):
        super().__init__(fmt=self._FMT, datefmt=self._DATE)


# ── Başlangıçta log klasörlerini sıfırla ─────────────────────────────────────

def _reset_log_dirs(sessionTimestamp: str) -> dict[str, str]:
    """
    logs/info, logs/error, logs/warning klasörlerini siler ve yeniden oluşturur.
    Her klasörde oturuma ait tek bir .log dosyası açılır.
    Dosya yollarını döndürür.
    """
    paths: dict[str, str] = {}

    for sub in _LOG_SUBDIRS:
        dirPath = os.path.join(_LOG_ROOT, sub)

        if os.path.exists(dirPath):
            shutil.rmtree(dirPath)
        os.makedirs(dirPath, exist_ok=True)

        fileName = f"{sessionTimestamp}.log"
        paths[sub] = os.path.join(dirPath, fileName)

    return paths


# ── Root logger kurulumu ─────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    """
    Uygulamanın başında bir kez çağrılır.
    - logs/ altındaki klasörleri sıfırlar.
    - Dosya handler'larını ekler (info, error+critical, warning).
    - Terminal handler'ı yalnızca INFO ve ERROR/CRITICAL gösterir.
    - 'mapin' adlı kök logger'ı döndürür.
    """
    sessionTs = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    logPaths  = _reset_log_dirs(sessionTs)

    rootLogger = logging.getLogger("mapin")
    rootLogger.setLevel(logging.DEBUG)

    rootLogger.handlers.clear()

    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logging.INFO)
    consoleHandler.addFilter(_LevelFilter(allowed={logging.INFO, logging.ERROR, logging.CRITICAL}))
    consoleHandler.setFormatter(_ColorFormatter())
    rootLogger.addHandler(consoleHandler)

    infoHandler = logging.FileHandler(logPaths["info"], encoding="utf-8")
    infoHandler.setLevel(logging.DEBUG)
    infoHandler.addFilter(_LevelFilter(allowed={logging.DEBUG, logging.INFO}))
    infoHandler.setFormatter(_FileFormatter())
    rootLogger.addHandler(infoHandler)

    warnHandler = logging.FileHandler(logPaths["warning"], encoding="utf-8")
    warnHandler.setLevel(logging.WARNING)
    warnHandler.addFilter(_LevelFilter(allowed={logging.WARNING}))
    warnHandler.setFormatter(_FileFormatter())
    rootLogger.addHandler(warnHandler)

    errorHandler = logging.FileHandler(logPaths["error"], encoding="utf-8")
    errorHandler.setLevel(logging.ERROR)
    errorHandler.addFilter(_LevelFilter(allowed={logging.ERROR, logging.CRITICAL}))
    errorHandler.setFormatter(_FileFormatter())
    rootLogger.addHandler(errorHandler)

    rootLogger.propagate = False

    rootLogger.info(f"Oturum başladı — {sessionTs}")
    rootLogger.info(f"Log klasörü: {_LOG_ROOT}")

    return rootLogger


# ── Seviye filtresi ──────────────────────────────────────────────────────────

class _LevelFilter(logging.Filter):
    """Yalnızca izin verilen seviyeleri geçirir."""

    def __init__(self, allowed: set[int]):
        super().__init__()
        self._allowed = allowed

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno in self._allowed


# ── Modül bazlı logger alma ───────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """
    Modüle özel logger döndürür.
    Örnek: get_logger("MapsScraper") → logging.Logger("mapin.MapsScraper")
    """
    return logging.getLogger(f"mapin.{name}")
