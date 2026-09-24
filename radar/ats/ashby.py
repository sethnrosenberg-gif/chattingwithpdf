"""Ashby public posting API."""
from __future__ import annotations

import re

from ..extract import Pay
from ..http import client
from ..models import Posting
from .base import build_posting, pay_from_range

API = "https://api.ashbyhq.com/posting-api/job-board"
URL_RX = re.compile(r"jobs\.ashbyhq\.com/(?P<board>[^/?#]+)/(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
UUID_RX = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

# employer career sites that front an Ashby board
FRONTED = {"harvey.ai": "harvey", "www.harvey.ai": "harvey"}


def parse_url(url: str) -> tuple[str, str] | None:
    m = URL_RX.search(url)
    if m:
        return m.group("board"), m.group("id").lower()
    for host, board in FRONTED.items():
        if f"//{host}/" in url:
            u = UUID_RX.search(url)
            if u:
                return board, u.group(0).lower()
    return None


def _board(board: str):
    return client().get(f"{API}/{board}", params={"includeCompensation": "true"})


def probe(board: str) -> tuple[bool, int]:
    r = _board(board)
    if r.ok:
        try:
            return True, len(r.json().get("jobs", []))
        except ValueError:
            return False, 0
    return False, 0


def _pay(comp: dict | None) -> Pay | None:
    if not comp:
        return None
    comps = comp.get("summaryComponents") or []
    salary = next((c for c in comps if c.get("compensationType") == "Salary" and (c.get("minValue") or c.get("maxValue"))), None)
    commission = any(c.get("compensationType") == "Commission" for c in comps)
    summary = comp.get("compensationTierSummary") or ""
    ote = commission or bool(re.search(r"\bOTE\b", summary))
    if not salary:
        return None
    interval = (salary.get("interval") or "1 YEAR").upper()
    period = "hour" if "HOUR" in interval else "month" if "MONTH" in interval else "year"
    p = pay_from_range(salary.get("minValue"), salary.get("maxValue"), period=period, ote=ote,
                       source="ashby:compensation", currency=salary.get("currencyCode") or "USD")
    if p:
        extras = []
        if any(c.get("compensationType") == "Bonus" for c in comps) or "Bonus" in summary:
            extras.append("bonus")
        if any("Equity" in (c.get("compensationType") or "") for c in comps) or "Equity" in summary:
            extras.append("equity")
        if commission:
            extras.append("commission")
        p.extras = " + ".join(extras)
    return p


def _posting(board: str, j: dict, company: str, source: str) -> Posting:
    locs = [j.get("location") or ""]
    for s in j.get("secondaryLocations") or []:
        locs.append(s.get("location") or "")
    addr = ((j.get("address") or {}).get("postalAddress") or {})
    country = addr.get("addressCountry") or None
    if country in ("USA", "United States", "US"):
        country = "US"
    wp = (j.get("workplaceType") or "").lower()
    wp = {"onsite": "onsite", "hybrid": "hybrid", "remote": "remote"}.get(wp, "")
    p = build_posting(
        ats="ashby", board=board, job_id=j["id"], company=company, title=j.get("title", ""),
        url=j.get("jobUrl") or f"https://jobs.ashbyhq.com/{board}/{j['id']}",
        description_html=j.get("descriptionHtml"), description_text=j.get("descriptionPlain"),
        locations=locs, remote_flag=bool(j.get("isRemote")), country=country if len(locs) <= 1 else None,
        workplace=wp or ("remote" if j.get("isRemote") else None), pay=_pay(j.get("compensation")),
        posted=j.get("publishedAt"), apply_url=j.get("applyUrl"), source=source,
        extra_pay_text=((j.get("compensation") or {}).get("compensationTierSummary") or ""),
        evidence=f"Ashby API lists job on board '{board}'",
    )
    return p


def pull(board: str, company: str, source: str = "board:ashby") -> tuple[str, list[Posting]]:
    r = _board(board)
    if r.blocked or r.error:
        return r.describe(), []
    if r.status == 404:
        return "board not found", []
    if not r.ok:
        return r.describe(), []
    jobs = [j for j in r.json().get("jobs", []) if j.get("isListed", True)]
    return "ok", [_posting(board, j, company, source) for j in jobs]


def verify(board: str, job_id: str, company: str, source: str = "verify") -> Posting | None:
    r = _board(board)
    if not r.ok:
        raise RuntimeError(f"ashby {board}: {r.describe()}")
    for j in r.json().get("jobs", []):
        if j.get("id", "").lower() == job_id.lower():
            p = _posting(board, j, company, source)
            p.status_evidence = f"Ashby API lists job {job_id} on board '{board}' on this run"
            return p
    return None
