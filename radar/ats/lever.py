"""Lever public postings API."""
from __future__ import annotations

import re

from ..http import client
from ..models import Posting
from .base import build_posting, pay_from_range

API = "https://api.lever.co/v0/postings"
URL_RX = re.compile(r"jobs\.(?:eu\.)?lever\.co/(?P<board>[^/?#]+)/(?P<id>[0-9a-f-]{36})", re.I)


def parse_url(url: str) -> tuple[str, str] | None:
    m = URL_RX.search(url)
    return (m.group("board"), m.group("id")) if m else None


def probe(board: str) -> tuple[bool, int]:
    r = client().get(f"{API}/{board}", params={"mode": "json"})
    if r.ok:
        try:
            d = r.json()
            return isinstance(d, list), len(d) if isinstance(d, list) else 0
        except ValueError:
            return False, 0
    return False, 0


def _posting(board: str, j: dict, company: str, source: str) -> Posting:
    cats = j.get("categories") or {}
    locs = list(cats.get("allLocations") or []) or [cats.get("location") or ""]
    sections = "\n\n".join(f"{l.get('text', '')}\n{l.get('content', '')}" for l in j.get("lists") or [])
    desc_html = (j.get("description") or "") + "\n" + sections + "\n" + (j.get("additional") or "")
    sr = j.get("salaryRange") or {}
    interval = (sr.get("interval") or "").lower()
    pay = pay_from_range(
        sr.get("min"), sr.get("max"), period="hour" if "hour" in interval else "month" if "month" in interval else "year",
        ote=bool(re.search(r"\bOTE\b|commission", j.get("salaryDescriptionPlain") or "", re.I)),
        source="lever:salaryRange", currency=sr.get("currency") or "USD",
    ) if sr else None
    wp = (j.get("workplaceType") or "").lower()
    return build_posting(
        ats="lever", board=board, job_id=j["id"], company=company, title=j.get("text", ""),
        url=j.get("hostedUrl") or f"https://jobs.lever.co/{board}/{j['id']}", description_html=desc_html,
        locations=locs, remote_flag=wp == "remote", country=j.get("country"),
        workplace={"remote": "remote", "hybrid": "hybrid", "on-site": "onsite", "onsite": "onsite"}.get(wp),
        pay=pay, posted=j.get("createdAt"), apply_url=j.get("applyUrl"), source=source,
        extra_pay_text=j.get("salaryDescriptionPlain") or "",
        evidence=f"Lever API lists job on board '{board}'",
    )


def pull(board: str, company: str, source: str = "board:lever") -> tuple[str, list[Posting]]:
    r = client().get(f"{API}/{board}", params={"mode": "json"})
    if r.blocked or r.error:
        return r.describe(), []
    if r.status == 404:
        return "board not found", []
    if not r.ok:
        return r.describe(), []
    return "ok", [_posting(board, j, company, source) for j in r.json()]


def verify(board: str, job_id: str, company: str, source: str = "verify") -> Posting | None:
    r = client().get(f"{API}/{board}/{job_id}", params={"mode": "json"})
    if r.status == 404:
        return None
    if not r.ok:
        raise RuntimeError(f"lever {board}/{job_id}: {r.describe()}")
    p = _posting(board, r.json(), company, source)
    p.status_evidence = f"Lever API returned job {job_id} on this run"
    return p
