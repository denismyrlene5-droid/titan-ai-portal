from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
from threading import Lock

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "titan_portal.sqlite3"
_lock = Lock()

def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _lock, connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            stage TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL,
            source_name TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            summary_json TEXT
        )
        """)
        conn.commit()

def create_job(job_id: str, source_type: str, source_name: str):
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO jobs(id,stage,progress,message,source_type,source_name) VALUES(?,?,?,?,?,?)",
            (job_id, "preparing", 0, "Preparing video", source_type, source_name),
        )
        conn.commit()

def update_job(job_id: str, stage: str, progress: int, message: str, summary=None):
    with _lock, connect() as conn:
        conn.execute(
            """UPDATE jobs SET stage=?, progress=?, message=?, summary_json=?,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (stage, int(progress), message, json.dumps(summary) if summary is not None else None, job_id),
        )
        conn.commit()

def get_job(job_id: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["summary"] = json.loads(result["summary_json"]) if result.get("summary_json") else None
    result.pop("summary_json", None)
    return result

def list_jobs(limit: int = 20):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["summary"] = json.loads(item["summary_json"]) if item.get("summary_json") else None
        item.pop("summary_json", None)
        out.append(item)
    return out
