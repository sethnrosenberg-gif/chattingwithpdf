"""Hacker News "Ask HN: Who is hiring?" threads (Algolia API), last three months."""
from __future__ import annotations

import html as htmllib
import re

from ..http import client
from ..keywords import relevance
from ..leads import add_leads
from ..models import Lead
from ..runlog import record_channel
from ..textutil import html_to_text
from .common import ATS_URL, keep_location

DOMAIN = re.compile(
    r"legal|counsel|attorney|lawyer|regulat|compliance counsel|policy|credit|underwrit|litigation|fintech|payments|"
    r"crypto|stablecoin|digital assets|prediction market|ai governance|trust (&|and) safety",
    re.I,
)
ROLE_SPLIT = re.compile(r"\s*[,;/]\s*|\s+and\s+|\s*\|\s*")


def run() -> dict:
    r = client().get("https://hn.algolia.com/api/v1/search_by_date", params={"tags": "story,author_whoishiring", "hitsPerPage": 20})
    stories = [h for h in r.json().get("hits", []) if h.get("title", "").startswith("Ask HN: Who is hiring")][:3] if r.ok else []
    queried, scanned, matched, leads, failures = 1, 0, 0, [], []
    for s in stories:
        it = client().get(f"https://hn.algolia.com/api/v1/items/{s['objectID']}")
        queried += 1
        if not it.ok:
            failures.append(f"thread {s['objectID']}: {it.describe()}")
            continue
        month = s["title"].split("(")[-1].rstrip(")")
        for c in it.json().get("children", []):
            raw = c.get("text") or ""
            if not raw:
                continue
            scanned += 1
            text = html_to_text(raw)
            if not DOMAIN.search(text):
                continue
            first = text.split("\n", 1)[0]
            parts = [p.strip() for p in first.split("|")]
            company = parts[0] if parts else ""
            loc_part = next((p for p in parts[1:] if re.search(r"remote|new york|nyc|onsite|hybrid", p, re.I)), "")
            if not loc_part or not keep_location(loc_part):
                continue
            role_text = " | ".join(parts[1:])
            roles = [x for x in ROLE_SPLIT.split(role_text) if x and relevance(x, text)[0]]
            if not roles:
                continue
            matched += 1
            urls = [htmllib.unescape(u) for u in re.findall(r'href="([^"]+)"', raw)]
            ats = next((u for u in urls if ATS_URL.match(u)), None)
            url = ats or (urls[0] if urls else f"https://news.ycombinator.com/item?id={c['id']}")
            for role in roles[:4]:
                leads.append(Lead(source="hn_whoishiring", url=url, company=company, title=role, location=loc_part,
                                  note=f"{month}: {re.sub(r'\s+', ' ', text)[:200]}"))
    written = add_leads(leads)
    record_channel("discover:hn", queried=queried, candidates=len(leads), failures=failures,
                   notes=f"{len(stories)} threads, {scanned} comments scanned, {matched} matched")
    return {"threads": [s["title"] for s in stories], "scanned": scanned, "matched": matched, "leads": written}
