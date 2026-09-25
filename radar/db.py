"""SQLite storage (data/jobs.sqlite).

postings    latest known state of every posting we have ever verified (by key)
snapshots   one row per posting per run: what the output showed that day (drives diffs and †)
board_jobs  every job pulled from every full board, all locations (Phase 2 raw material)
leads       discovery-channel candidates (mirrors data/leads.jsonl)
judgments   subagent judgment calls, cached by posting key + description hash
runs        run metadata
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager

from . import config
from .models import Posting

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS postings (
  key TEXT PRIMARY KEY, dedupe_key TEXT, company TEXT, title TEXT, url TEXT, status TEXT,
  first_seen TEXT, last_seen TEXT, last_verified TEXT, data TEXT
);
CREATE INDEX IF NOT EXISTS postings_dedupe ON postings(dedupe_key);
CREATE TABLE IF NOT EXISTS snapshots (
  run_id TEXT, key TEXT, dedupe_key TEXT, bucket TEXT, status TEXT, company TEXT, title TEXT, url TEXT,
  location TEXT, pay_min REAL, pay_max REAL, pay_type TEXT, pay_display TEXT, years_required INTEGER,
  jd_required TEXT, fit_score INTEGER, hard_exclude_reason TEXT, poor_reason TEXT, is_new INTEGER,
  PRIMARY KEY (run_id, key)
);
CREATE TABLE IF NOT EXISTS board_jobs (
  ats TEXT, board TEXT, job_id TEXT, company TEXT, title TEXT, location TEXT, loc_bucket TEXT,
  url TEXT, relevant INTEGER, relevance_reason TEXT, first_seen TEXT, last_seen TEXT, data TEXT,
  PRIMARY KEY (ats, board, job_id)
);
CREATE TABLE IF NOT EXISTS leads (
  url TEXT, source TEXT, company TEXT, title TEXT, location TEXT, note TEXT, found_at TEXT,
  verified_key TEXT, verify_status TEXT,
  PRIMARY KEY (url, source)
);
CREATE TABLE IF NOT EXISTS judgments (
  key TEXT, desc_hash TEXT, data TEXT, created_at TEXT, PRIMARY KEY (key, desc_hash)
);
"""

_local = threading.local()


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        config.DATA.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(config.DB_PATH, timeout=60)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        _local.conn = c
    return c


_write_lock = threading.Lock()


@contextmanager
def tx():
    """One writer at a time within the process (threads share the file); busy timeout covers other processes."""
    c = conn()
    with _write_lock:
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def upsert_posting(p: Posting) -> None:
    now = config.run_id()
    with tx() as c:
        row = c.execute("SELECT first_seen FROM postings WHERE key=?", (p.key,)).fetchone()
        first = row["first_seen"] if row else now
        c.execute(
            "INSERT OR REPLACE INTO postings VALUES (?,?,?,?,?,?,?,?,?,?)",
            (p.key, p.dedupe_key(), p.company, p.title, p.url, p.status, first, now,
             p.verified_at, p.model_dump_json()),
        )


def get_posting(key: str) -> Posting | None:
    row = conn().execute("SELECT data FROM postings WHERE key=?", (key,)).fetchone()
    return Posting.model_validate_json(row["data"]) if row else None


def write_snapshot(run_id: str, rows: list[tuple[Posting, bool]]) -> None:
    with tx() as c:
        c.execute("DELETE FROM snapshots WHERE run_id=?", (run_id,))
        c.executemany(
            "INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (run_id, p.key, p.dedupe_key(), p.bucket, p.status, p.company, p.title, p.url, p.location,
                 p.pay_min, p.pay_max, p.pay_type, p.pay_display, p.years_required, p.jd_required,
                 p.fit_score, p.hard_exclude_reason, p.poor_reason, int(is_new))
                for p, is_new in rows
            ],
        )


def previous_run(run_id: str) -> str | None:
    row = conn().execute(
        "SELECT MAX(run_id) AS r FROM snapshots WHERE run_id < ?", (run_id,)
    ).fetchone()
    return row["r"] if row and row["r"] else None


def snapshot(run_id: str) -> list[sqlite3.Row]:
    return conn().execute("SELECT * FROM snapshots WHERE run_id=?", (run_id,)).fetchall()


def upsert_board_jobs(rows: list[dict]) -> None:
    now = config.run_id()
    with tx() as c:
        for r in rows:
            prev = c.execute(
                "SELECT first_seen FROM board_jobs WHERE ats=? AND board=? AND job_id=?",
                (r["ats"], r["board"], r["job_id"]),
            ).fetchone()
            c.execute(
                "INSERT OR REPLACE INTO board_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["ats"], r["board"], r["job_id"], r.get("company"), r.get("title"), r.get("location"),
                 r.get("loc_bucket"), r.get("url"), int(bool(r.get("relevant"))), r.get("relevance_reason", ""),
                 prev["first_seen"] if prev else now, now, json.dumps(r.get("raw") or {})[:200_000]),
            )


def get_judgment(key: str, desc_hash: str) -> dict | None:
    row = conn().execute("SELECT data FROM judgments WHERE key=? AND desc_hash=?", (key, desc_hash)).fetchone()
    if row:
        return json.loads(row["data"])
    # fall back to the latest judgment for this key if the description changed only cosmetically
    return None


def put_judgment(key: str, desc_hash: str, data: dict) -> None:
    with tx() as c:
        c.execute(
            "INSERT OR REPLACE INTO judgments VALUES (?,?,?,?)",
            (key, desc_hash, json.dumps(data), config.run_id()),
        )
