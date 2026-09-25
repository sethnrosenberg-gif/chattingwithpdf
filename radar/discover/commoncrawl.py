"""ATS-wide discovery via the Common Crawl CDX index.

index.commoncrawl.org's robots.txt disallows everything; the user approved exempting it
(RADAR_ROBOTS_EXEMPT_HOSTS). data.commoncrawl.org stays off-limits.

Finds Greenhouse / Lever / Ashby board tokens in the two latest crawls, then pulls each board
and keeps relevant US postings. State in data/cc_boards.json spreads the work across weekly runs;
boards with hits go to data/discovered_boards.csv, which Phase 2 pulls every week.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from .. import config
from ..ats import ashby, greenhouse, lever
from ..http import channel, client, current_channel
from ..leads import add_leads
from ..runlog import record_channel
from .common import posting_leads

PATTERNS = {
    "greenhouse": ["job-boards.greenhouse.io/*", "boards.greenhouse.io/*"],
    "lever": ["jobs.lever.co/*"],
    "ashby": ["jobs.ashbyhq.com/*"],
}
PULL = {"greenhouse": greenhouse.pull, "lever": lever.pull, "ashby": ashby.pull}
SKIP_TOKENS = {"embed", "static", "favicon.ico", "robots.txt", "", "api", "v1", "assets", "_next", "sitemap.xml"}
STATE = config.DATA / "cc_boards.json"
BOARDS_CSV = config.DATA / "discovered_boards.csv"
MAX_PAGES = int(os.getenv("RADAR_CC_MAX_PAGES") or 40)
MAX_TOKENS = int(os.getenv("RADAR_CC_MAX_TOKENS") or 1500)
RECHECK_DAYS = 28


def _crawls() -> list[str]:
    r = client().get("https://index.commoncrawl.org/collinfo.json")
    return [c["cdx-api"] for c in r.json()[:2]] if r.ok else []


def _tokens(api: str, pattern: str, failures: list[str]) -> tuple[set[str], int]:
    toks: set[str] = set()
    r = client().get(api, params={"url": pattern, "output": "json", "fl": "url", "showNumPages": "true"})
    if not r.ok:
        failures.append(f"{api} {pattern}: {r.describe()}")
        return toks, 1
    try:
        pages = int(json.loads(r.text.splitlines()[0]).get("pages", 1))
    except (ValueError, IndexError, AttributeError):
        pages = 1
    host = pattern.split("/")[0]
    n = 1
    for page in range(min(pages, MAX_PAGES)):
        pr = client().get(api, params={"url": pattern, "output": "json", "fl": "url", "page": page})
        n += 1
        if not pr.ok:
            failures.append(f"{api} {pattern} page {page}: {pr.describe()}")
            continue
        for line in pr.text.splitlines():
            m = re.search(re.escape(host) + r"/([\w.-]+)", line)
            if m and m.group(1).lower() not in SKIP_TOKENS:
                toks.add(m.group(1).lower())
    if pages > MAX_PAGES:
        failures.append(f"{pattern}: capped at {MAX_PAGES} of {pages} index pages")
    return toks, n


def run() -> dict:
    today = config.run_id()
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    failures: list[str] = []
    queried = 0
    apis = _crawls()
    queried += 1
    if not apis:
        record_channel("discover:commoncrawl", queried=queried, failures=["collinfo.json unavailable"])
        return {"error": "no crawls"}
    fresh: dict[str, set[str]] = {}
    for ats, pats in PATTERNS.items():
        fresh[ats] = set()
        for api in apis:
            for pat in pats:
                t, n = _tokens(api, pat, failures)
                queried += n
                fresh[ats] |= t
        st = state.setdefault(ats, {})
        for tok in fresh[ats]:
            st.setdefault(tok, {"first_seen": today, "last_checked": None, "jobs": 0, "relevant": 0})

    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=RECHECK_DAYS)).isoformat()
    ch = current_channel()

    def sweep(ats: str) -> tuple[list, int, int]:
        with channel(ch):
            st = state[ats]
            due = [t for t, v in st.items() if not v["last_checked"] or v["last_checked"] < cutoff]
            due.sort(key=lambda t: (t not in fresh[ats], t))
            todo, leads = due[:MAX_TOKENS], []
            for tok in todo:
                status, ps = PULL[ats](tok, tok, f"commoncrawl:{ats}")
                ls = posting_leads(ps, "commoncrawl")
                if ls and ats == "greenhouse":
                    name = greenhouse.board_name(tok) or tok
                    for l in ls:
                        l.company = name
                st[tok].update(last_checked=today, jobs=len(ps), relevant=len(ls), company=ls[0].company if ls else tok)
                leads += ls
            return leads, len(todo), len(due) - len(todo)

    with ThreadPoolExecutor(3) as ex:
        res = dict(zip(PATTERNS, ex.map(sweep, PATTERNS)))
    STATE.write_text(json.dumps(state, indent=0), encoding="utf-8")

    rows = [{"ats": a, "board": t, "company": v.get("company", t), "relevant_hits": v["relevant"], "jobs": v["jobs"],
             "first_seen": v["first_seen"], "last_checked": v["last_checked"]}
            for a, st in state.items() for t, v in st.items() if v["relevant"]]
    with open(BOARDS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ats", "board", "company", "relevant_hits", "jobs", "first_seen", "last_checked"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (-r["relevant_hits"], r["board"])))

    leads = [l for v in res.values() for l in v[0]]
    written = add_leads(leads)
    checked = sum(v[1] for v in res.values())
    pending = {a: v[2] for a, v in res.items()}
    record_channel("discover:commoncrawl", queried=queried + checked, candidates=written, failures=failures,
                   notes=f"user-approved robots exemption for index.commoncrawl.org; tokens found "
                         f"{ {a: len(t) for a, t in fresh.items()} }; boards checked {checked}; pending {pending}; "
                         f"boards with hits {len(rows)}")
    return {"tokens": {a: len(t) for a, t in fresh.items()}, "checked": checked, "pending": pending,
            "boards_with_hits": len(rows), "leads": written, "failures": failures[:10]}
