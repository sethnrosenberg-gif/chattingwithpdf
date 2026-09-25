"""Greenhouse public Job Board API."""
from __future__ import annotations

import re

from ..extract import Pay
from ..http import client, probe_client
from ..models import Posting
from ..textutil import html_to_text
from .base import build_posting, pay_from_range

API = "https://boards-api.greenhouse.io/v1/boards"
URL_RX = re.compile(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_app\?for=)?(?P<board>[\w.-]+)/jobs/(?P<id>\d+)", re.I)
EMBED_RX = re.compile(r"greenhouse\.io/embed/job_app\?(?=.*for=(?P<board>[\w.-]+))(?=.*token=(?P<id>\d+))", re.I)


def parse_url(url: str) -> tuple[str, str] | None:
    m = URL_RX.search(url) or EMBED_RX.search(url)
    if m:
        return m.group("board"), m.group("id")
    m = re.search(r"[?&]gh_jid=(\d+)", url)
    if m:
        return "", m.group(1)
    return None


def board_name(board: str) -> str | None:
    r = client().get(f"{API}/{board}")
    if r.ok:
        try:
            return r.json().get("name")
        except ValueError:
            return None
    return None


def probe(board: str) -> tuple[bool, int]:
    r = probe_client().get(f"{API}/{board}/jobs")
    if r.ok:
        try:
            return True, len(r.json().get("jobs", []))
        except ValueError:
            return False, 0
    return False, 0


def _pay(ranges: list[dict] | None) -> Pay | None:
    if not ranges:
        return None
    pick = next((r for r in ranges if re.search(r"new york|nyc|\bny\b", (r.get("title") or "") + " " + (r.get("blurb") or ""), re.I)), ranges[0])
    lo, hi = pick.get("min_cents"), pick.get("max_cents")
    if lo is None and hi is None:
        return None
    txt = " ".join(str(pick.get(k) or "") for k in ("title", "blurb", "description"))
    hourly = bool(re.search(r"hour", txt, re.I)) or (hi or lo or 0) / 100 < 1000
    ote = bool(re.search(r"\bOTE\b|on[- ]target|commission", txt, re.I))
    return pay_from_range(
        (lo or hi) / 100, (hi or lo) / 100, period="hour" if hourly else "year", ote=ote,
        source="greenhouse:pay_input_ranges", currency=pick.get("currency_type") or "USD",
    )


def _posting(board: str, j: dict, company: str, source: str, pay: Pay | None = None) -> Posting:
    locs = [(j.get("location") or {}).get("name", "")]
    for o in j.get("offices") or []:
        if o.get("location"):  # office "name" is often a label like "Professional", not a place
            locs.append(o["location"])
    url = j.get("absolute_url") or f"https://job-boards.greenhouse.io/{board}/jobs/{j['id']}"
    content = j.get("content") or ""
    pay_text = ""
    if pay is None and j.get("pay_input_ranges"):
        pay = _pay(j.get("pay_input_ranges"))
    for mf in j.get("metadata") or []:
        if mf and re.search(r"salary|pay|compensation", str(mf.get("name")), re.I) and mf.get("value"):
            pay_text += f" Salary range: {mf.get('value')}"
    return build_posting(
        ats="greenhouse", board=board, job_id=str(j["id"]), company=company, title=j.get("title", ""),
        url=url, description_html=content, locations=locs, pay=pay, posted=j.get("first_published") or j.get("updated_at"),
        apply_url=url, source=source, extra_pay_text=pay_text,
        evidence=f"Greenhouse API lists job {j['id']} on board '{board}'",
    )


def pull(board: str, company: str, source: str = "board:greenhouse") -> tuple[str, list[Posting]]:
    r = client().get(f"{API}/{board}/jobs", params={"content": "true"})
    if r.blocked or r.error:
        return r.describe(), []
    if r.status == 404:
        return "board not found", []
    if not r.ok:
        return r.describe(), []
    jobs = r.json().get("jobs", [])
    return "ok", [_posting(board, j, company, source) for j in jobs]


def verify(board: str, job_id: str, company: str, source: str = "verify") -> Posting | None:
    """Fetch one job with pay transparency. Returns a closed stub on 404."""
    r = client().get(f"{API}/{board}/jobs/{job_id}", params={"pay_transparency": "true"})
    if r.status == 404:
        return None
    if not r.ok:
        raise RuntimeError(f"greenhouse {board}/{job_id}: {r.describe()}")
    j = r.json()
    p = _posting(board, j, company, source, pay=_pay(j.get("pay_input_ranges")))
    p.status_evidence = f"Greenhouse API returned job {job_id} (board '{board}') on this run"
    return p


def enrich_pay(p: Posting) -> Posting:
    """Board listings omit pay_input_ranges; pull them for candidates that matter."""
    if p.ats != "greenhouse" or not p.job_id or p.pay_source.startswith("greenhouse"):
        return p
    r = client().get(f"{API}/{p.board}/jobs/{p.job_id}", params={"pay_transparency": "true"})
    if r.ok:
        pay = _pay(r.json().get("pay_input_ranges"))
        if pay and pay.min:
            from ..extract import pay_display, pay_extras

            pay.extras = pay_extras(p.description)
            p.pay_min, p.pay_max, p.pay_type, p.pay_period = pay.min, pay.max, pay.type, pay.period
            p.pay_source, p.pay_extras, p.pay_display = pay.source, pay.extras, pay_display(pay)
    elif r.status == 404:
        p.status = "closed"
        p.status_evidence = "Greenhouse API returned 404 for the job on this run"
    return p


__all__ = ["pull", "verify", "probe", "parse_url", "board_name", "enrich_pay", "html_to_text"]
