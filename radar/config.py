"""Paths, environment and run identity shared by every module."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
OUT = ROOT / "out"
CACHE = ROOT / "cache"
SEEDS = ROOT / "seeds"
DB_PATH = DATA / "jobs.sqlite"
LEADS_PATH = DATA / "leads.jsonl"
COMPANIES_CSV = SEEDS / "companies.csv"
SEED_LIST = SEEDS / "current_list.md"

CONTACT_EMAIL = os.getenv("RADAR_CONTACT_EMAIL") or "sethnrosenberg@gmail.com"
UA_TOKEN = "JobRadar"
USER_AGENT = f"{UA_TOKEN}/0.1 (personal job-search tool; read-only; contact: {CONTACT_EMAIL})"

CACHE_TTL_HOURS = float(os.getenv("RADAR_CACHE_TTL_HOURS") or 20)
ROBOTS_EXEMPT_HOSTS = {
    h.strip().lower() for h in (os.getenv("RADAR_ROBOTS_EXEMPT_HOSTS") or "").split(",") if h.strip()
}
MIN_HOST_DELAY = 1.0  # seconds between requests to one host, across all processes


def today() -> str:
    return dt.date.today().isoformat()


def run_id() -> str:
    """One run per day. Override with RADAR_RUN_ID to replay or to share an id with subagents."""
    return os.getenv("RADAR_RUN_ID") or today()


def run_dir() -> Path:
    d = DATA / "runs" / run_id()
    d.mkdir(parents=True, exist_ok=True)
    return d


def env(name: str) -> str | None:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else None


for _d in (DATA, OUT, CACHE):
    _d.mkdir(parents=True, exist_ok=True)
