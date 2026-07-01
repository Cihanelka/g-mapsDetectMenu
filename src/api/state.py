"""
Uygulama genelinde paylaşılan durum
Created by: Mapin Data
Created at: 2026-04-21
Subject: Aktif toplu iş takibi (BulkJob), her sonuç anında diske yazılarak
         kalıcı hale getirilir (checkpoint) ve son 50 sorgu geçmişi (dosyada kalıcı).

Checkpoint mekanizması:
  Her URL tamamlandığında ilgili işin tüm durumu jobs/{job_id}.json dosyasına
  yazılır. Uygulama beklenmedik şekilde durursa (yarıda kalırsa), sunucu yeniden
  başlatıldığında bitmemiş checkpoint dosyaları otomatik bulunup kaldığı yerden
  devam ettirilir (bkz. loadIncompleteJobCheckpoints / server.py lifespan).
"""

import json
import os
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

_log = get_logger("JobState")

_lock = threading.Lock()

# job_id → BulkJob
_jobs: Dict[str, "BulkJob"] = {}

# Kalıcı geçmiş dosyası
_HISTORY_FILE = "query_history.json"

# Toplu iş checkpoint klasörü — her iş için ayrı JSON dosyası
_JOBS_DIR = "jobs"

# FIFO geçmiş: en yeni başta (appendleft)
_history: deque = deque(maxlen=50)


def _loadHistoryFromFile() -> None:
    """Başlangıçta geçmişi dosyadan yükle."""
    global _history
    if not os.path.exists(_HISTORY_FILE):
        return
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            _history = deque(data[:50], maxlen=50)
    except Exception:
        pass


def _saveHistoryToFile() -> None:
    """Geçmişi dosyaya yaz (kilit altında çağrılmalı)."""
    try:
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(list(_history), f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_loadHistoryFromFile()


@dataclass
class BulkJob:
    job_id: str
    toplam: int
    tamamlanan: int = 0
    basarisiz: int = 0
    sonuclar: Dict[str, Any] = field(default_factory=dict)
    baslangic: datetime = field(default_factory=datetime.now)
    bitis: Optional[datetime] = None
    url_sirasi: List[str] = field(default_factory=list)
    id_map: Dict[str, str] = field(default_factory=dict)


# ── CHECKPOINT (ANLIK KAYIT) ────────────────────────────────────────────────

def _checkpointPath(jobId: str) -> str:
    return os.path.join(_JOBS_DIR, f"{jobId}.json")


def _jobToCheckpointDict(job: BulkJob) -> dict:
    return {
        "job_id": job.job_id,
        "toplam": job.toplam,
        "tamamlanan": job.tamamlanan,
        "basarisiz": job.basarisiz,
        "sonuclar": job.sonuclar,
        "baslangic": job.baslangic.isoformat(),
        "bitis": job.bitis.isoformat() if job.bitis else None,
        "url_sirasi": job.url_sirasi,
        "id_map": job.id_map,
    }


def _saveJobCheckpoint(job: BulkJob) -> None:
    """Job durumunu diske yazar (anlık kayıt). Kilit altında çağrılmalı."""
    try:
        os.makedirs(_JOBS_DIR, exist_ok=True)
        checkpointFile = _checkpointPath(job.job_id)
        tmpFile = checkpointFile + ".tmp"
        with open(tmpFile, "w", encoding="utf-8") as f:
            json.dump(_jobToCheckpointDict(job), f, ensure_ascii=False, indent=2)
        os.replace(tmpFile, checkpointFile)
    except Exception as e:
        _log.error(f"[Job {job.job_id}] Checkpoint kaydı başarısız: {e}")


def loadIncompleteJobCheckpoints() -> List[dict]:
    """
    jobs/ klasöründeki henüz bitmemiş (bitis=None) checkpoint dosyalarını okur.
    Sunucu başlangıcında yarıda kalan işleri devam ettirmek için kullanılır.
    """
    incomplete: List[dict] = []
    if not os.path.isdir(_JOBS_DIR):
        return incomplete

    for filename in os.listdir(_JOBS_DIR):
        if not filename.endswith(".json"):
            continue
        filePath = os.path.join(_JOBS_DIR, filename)
        try:
            with open(filePath, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
            if checkpoint.get("bitis") is None:
                incomplete.append(checkpoint)
        except Exception as e:
            _log.warning(f"Checkpoint okunamadı ({filename}): {e}")

    return incomplete


def restoreJobFromCheckpoint(checkpoint: dict) -> BulkJob:
    """Diskteki checkpoint'ten bellek içi BulkJob nesnesi geri kurar."""
    job = BulkJob(
        job_id=checkpoint["job_id"],
        toplam=checkpoint["toplam"],
        tamamlanan=checkpoint.get("tamamlanan", 0),
        basarisiz=checkpoint.get("basarisiz", 0),
        sonuclar=checkpoint.get("sonuclar", {}),
        baslangic=datetime.fromisoformat(checkpoint["baslangic"]),
        bitis=None,
        url_sirasi=checkpoint.get("url_sirasi", []),
        id_map=checkpoint.get("id_map", {}),
    )
    with _lock:
        _jobs[job.job_id] = job
    return job


def getRemainingUrls(job: BulkJob) -> List[str]:
    """Henüz sonucu kaydedilmemiş (tamamlanmamış) URL'leri döner."""
    return [
        url for url in job.url_sirasi
        if not url.startswith("__bulunmadi_") and url not in job.sonuclar
    ]


# ── İş Yönetimi ─────────────────────────────────────────────────────────────

def createJob(toplam: int, urls: List[str] = None, id_map: Dict[str, str] = None) -> BulkJob:
    jobId = uuid.uuid4().hex[:8]
    job = BulkJob(job_id=jobId, toplam=toplam, url_sirasi=urls or [], id_map=id_map or {})
    with _lock:
        _jobs[jobId] = job
        _saveJobCheckpoint(job)
    return job


def updateJob(jobId: str, url: str, result: Any, isSuccess: bool) -> None:
    with _lock:
        job = _jobs.get(jobId)
        if not job:
            return
        if isSuccess:
            job.tamamlanan += 1
        else:
            job.basarisiz += 1
        job.sonuclar[url] = result
        _saveJobCheckpoint(job)


def finishJob(jobId: str) -> None:
    with _lock:
        job = _jobs.get(jobId)
        if job:
            job.bitis = datetime.now()
            _saveJobCheckpoint(job)


def getJob(jobId: str) -> Optional[BulkJob]:
    with _lock:
        return _jobs.get(jobId)


# ── Geçmiş ──────────────────────────────────────────────────────────────────

def addHistory(entry: dict) -> None:
    with _lock:
        _history.appendleft(entry)
        _saveHistoryToFile()


def getHistory() -> List[dict]:
    with _lock:
        return list(_history)
