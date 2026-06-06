"""
Uygulama genelinde paylaşılan durum
Created by: Mapin Data
Created at: 2026-04-21
Subject: Aktif toplu iş takibi (BulkJob) ve son 50 sorgu geçmişi (dosyada kalıcı).
"""

import json
import os
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

_lock = threading.Lock()

# job_id → BulkJob
_jobs: Dict[str, "BulkJob"] = {}

# Kalıcı geçmiş dosyası
_HISTORY_FILE = "query_history.json"

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


# ── İş Yönetimi ─────────────────────────────────────────────────────────────

def createJob(toplam: int, urls: List[str] = None) -> BulkJob:
    jobId = uuid.uuid4().hex[:8]
    job = BulkJob(job_id=jobId, toplam=toplam, url_sirasi=urls or [])
    with _lock:
        _jobs[jobId] = job
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


def finishJob(jobId: str) -> None:
    with _lock:
        job = _jobs.get(jobId)
        if job:
            job.bitis = datetime.now()


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
