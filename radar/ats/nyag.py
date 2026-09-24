"""New York Attorney General postings: HTML listing pages that link to PDF announcements.

robots.txt disallows `?page=` pagination, so only the first page of each category is read
(each category page currently lists every open posting).
"""
from __future__ import annotations

import datetime as dt
import io
import re
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from ..http import client
from ..models import Posting
from .base import build_posting

BASE = "https://ag.ny.gov"
CATEGORIES = ["attorneys", "other", "fellowships", "investigators"]


def pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join((pg.extract_text() or "") for pg in reader.pages)
    except Exception as e:  # malformed PDFs shouldn't sink the run
        return f"[pdf text extraction failed: {e}]"


def listing(category: str) -> tuple[str, list[dict]]:
    r = client().get(f"{BASE}/job-postings/{category}")
    if not r.ok:
        return r.describe(), []
    tree = HTMLParser(r.text)
    rows = []
    for row in tree.css("div.views-row"):
        def field(name: str) -> str:
            n = row.css_first(f".views-field-field-job-post-{name} .field-content")
            return n.text(strip=True) if n else ""

        a = row.css_first(".views-field-title a")
        if not a:
            continue
        t = row.css_first("time")
        dtext = t.text(strip=True) if t else field("deadline")
        try:
            deadline = dt.datetime.strptime(dtext, "%B %d, %Y").date().isoformat()
        except ValueError:
            deadline = ""  # "Open until filled" and similar
        rows.append({
            "title": a.text(strip=True),
            "pdf": urljoin(BASE, a.attributes.get("href", "")),
            "bureau": field("bureau"),
            "location": field("location"),
            "deadline": deadline,
            "deadline_text": dtext,
            "ref": field("reference-number"),
            "category": category,
        })
    return "ok", rows


def all_listings() -> tuple[dict[str, str], list[dict]]:
    statuses, rows = {}, []
    for c in CATEGORIES:
        st, rs = listing(c)
        statuses[c] = st
        rows.extend(rs)
    return statuses, rows


def to_posting(entry: dict, source: str = "public:nyag", fetch_pdf: bool = True) -> Posting:
    text = ""
    if fetch_pdf:
        r = client().get(entry["pdf"])
        if r.ok:
            text = pdf_text(r.content)
    title = entry["title"]
    if entry.get("bureau") and entry["bureau"].split(" (")[0].lower() not in title.lower():
        title = f"{title}, {entry['bureau'].split(' (')[0]}"
    # NY state uses "hiring rate" + "location pay"; the regex picks the range, extras noted separately
    extra = ""
    m = re.search(r"\$\s?[\d,]+\s*(?:location|downstate)[^\n.]{0,40}", text, re.I)
    if m:
        extra = m.group(0)
    deadline = entry.get("deadline") or None
    p = build_posting(
        ats="nyag", board="ag.ny.gov", job_id=entry["ref"] or entry["pdf"].rsplit("/", 1)[-1],
        company="NY Attorney General", title=title, url=entry["pdf"], description_text=text,
        locations=[entry.get("location", "")], closes=deadline, source=source, apply_url=entry["pdf"],
        evidence=f"Listed on ag.ny.gov/job-postings/{entry['category']} (Ref {entry['ref']}, deadline {entry.get('deadline_text')}) on this run",
    )
    if extra:
        p.pay_extras = (p.pay_extras + f" + {extra.strip()}").strip(" +")
        p.pay_display += f" + {re.search(r'[$][\d,]+', extra).group(0)} location pay"
    if deadline and dt.date.fromisoformat(deadline) < dt.date.today():
        p.status = "closed"
        p.status_evidence = f"Deadline {entry.get('deadline_text')} has passed"
    return p


def ref_from_url(url: str) -> str | None:
    m = re.search(r"/([a-z-]+_[a-z]+_[a-z]+_\d{4})|/([a-z]+(?:[-_][a-z]+)+[-_]\d{4})", url, re.I)
    if not m:
        return None
    return (m.group(1) or m.group(2)).replace("-", "_").upper()


def verify(url: str, source: str = "verify") -> Posting | None:
    ref = ref_from_url(url)
    statuses, rows = all_listings()
    if not rows and any(v != "ok" for v in statuses.values()):
        raise RuntimeError("ag.ny.gov listing pages unavailable: " + ", ".join(f"{k} {v}" for k, v in statuses.items()))
    for e in rows:
        if ref and e["ref"].upper() == ref:
            return to_posting(e, source=source)
        if e["pdf"].split("?")[0] == url.split("?")[0]:
            return to_posting(e, source=source)
    return None
