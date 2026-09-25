"""Shared posting builder: every ATS adapter funnels through build_posting()."""
from __future__ import annotations

import datetime as dt
import html as htmllib
import re

from .. import config
from ..extract import Pay, best_bucket, jd_requirement, pay_display, pay_extras, pay_from_text, workplace_of, years_required
from ..models import Posting
from ..textutil import html_to_text


def pay_from_jsonld(jp: dict | None) -> Pay | None:
    if not jp:
        return None
    bs = jp.get("baseSalary") or jp.get("estimatedSalary")
    if isinstance(bs, list):
        bs = bs[0] if bs else None
    if not isinstance(bs, dict):
        return None
    val = bs.get("value") if isinstance(bs.get("value"), dict) else bs
    try:
        lo = val.get("minValue") if isinstance(val, dict) else None
        hi = val.get("maxValue") if isinstance(val, dict) else None
        single = val.get("value") if isinstance(val, dict) else bs.get("value")
        lo = float(lo) if lo not in (None, "") else (float(single) if isinstance(single, (int, float, str)) and str(single).replace(".", "").isdigit() else None)
        hi = float(hi) if hi not in (None, "") else lo
    except (TypeError, ValueError):
        return None
    if lo is None or lo <= 0:
        return None
    unit = str((val or {}).get("unitText") or bs.get("unitText") or "YEAR").upper()
    period = "hour" if "HOUR" in unit else "month" if "MONTH" in unit else "year"
    return Pay(lo, hi, "hourly" if period == "hour" else "base", period, bs.get("currency") or "USD", "jsonld:baseSalary")


def pay_from_range(lo: float | None, hi: float | None, *, period: str = "year", ote: bool = False, source: str, currency: str = "USD") -> Pay | None:
    if lo is None and hi is None:
        return None
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    ptype = "hourly" if period == "hour" else ("OTE" if ote else "base")
    return Pay(float(lo), float(hi), ptype, period, currency, source)


def _date(s: str | None) -> str | None:
    if not s:
        return None
    s = str(s)
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    if m:
        return m.group(0)
    for fmt in ("%a %b %d %H:%M:%S %Z %Y", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    if isinstance(s, (int, float)) or s.isdigit():
        ts = int(s)
        if ts > 10**11:
            ts //= 1000
        return dt.datetime.utcfromtimestamp(ts).date().isoformat()
    return None


def url_key(url: str) -> str:
    """Stable key for postings without an ATS id. Keeps the query string (Point72's job id lives there)
    but drops tracking parameters."""
    from urllib.parse import parse_qsl, urlencode, urlsplit

    u = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith(("utm_", "gh_src", "lever-source", "src", "ref"))]
    return "url:" + f"{u.netloc}{u.path}".lower().rstrip("/") + (("?" + urlencode(sorted(q))) if q else "")


def build_posting(
    *,
    ats: str,
    board: str | None,
    job_id: str | None,
    company: str,
    title: str,
    url: str,
    description_html: str | None = None,
    description_text: str | None = None,
    locations: list[str] | None = None,
    remote_flag: bool | None = None,
    country: str | None = None,
    workplace: str | None = None,
    pay: Pay | None = None,
    posted: str | None = None,
    closes: str | None = None,
    apply_url: str | None = None,
    status: str = "open",
    evidence: str = "",
    source: str = "",
    extra_pay_text: str = "",
) -> Posting:
    text = description_text if description_text is not None else html_to_text(description_html)
    text = (text or "").strip()
    locs = [l.strip() for l in (locations or []) if l and l.strip()]
    # de-dup while preserving order
    seen: set[str] = set()
    locs = [l for l in locs if not (l.lower() in seen or seen.add(l.lower()))]

    p = pay
    if p is None or p.min is None:
        p = pay_from_text((extra_pay_text + "\n" + text).strip())
    if not p.extras:
        p.extras = pay_extras(text + " " + extra_pay_text)
    if p.type == "base" and re.search(r"\bOTE\b|on[- ]target earnings", (extra_pay_text + " " + text)[:20000]):
        # a base figure alongside an explicit OTE mention: keep base but flag the OTE for the rubric
        p.extras = (p.extras + " + OTE mentioned").strip(" +")

    if not closes:
        m = re.search(
            r"(?:posting close date|closing date|application deadline|apply by|applications? (?:are )?due(?: by)?|deadline)[:\s]*"
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2},? \d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
            text, re.I,
        )
        if m:
            closes = m.group(1).replace(".", "").replace("Sept", "Sep").replace(",", ", ").replace(",  ", ", ")
            for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
                try:
                    closes = dt.datetime.strptime(closes.strip(), fmt).date().isoformat()
                    break
                except ValueError:
                    continue
    yrs, yrs_ctx = years_required(text)
    key = f"{ats}:{board}:{job_id}" if job_id else url_key(url)
    loc_join = "; ".join(locs)
    return Posting(
        key=key,
        company=company,
        title=re.sub(r"\s+", " ", htmllib.unescape(title or "")).strip(),
        url=url,
        apply_url=apply_url,
        ats=ats,
        board=board,
        job_id=str(job_id) if job_id else None,
        location=loc_join,
        locations=locs,
        workplace=workplace or workplace_of(loc_join + " " + text[:600]),
        loc_bucket=best_bucket(locs, remote_flag=remote_flag, country=country),
        pay_min=p.min,
        pay_max=p.max,
        pay_type=p.type,
        pay_period=p.period,
        pay_currency=p.currency,
        pay_extras=p.extras,
        pay_source=p.source,
        pay_display=pay_display(p),
        years_required=yrs,
        years_text=yrs_ctx,
        jd_required=jd_requirement(text, title),
        posted_date=_date(posted),
        closes_date=_date(closes),
        description=text,
        status=status,
        status_evidence=evidence,
        verified_at=config.run_id() if status in ("open", "closed") else None,
        sources=[source] if source else [],
    )
