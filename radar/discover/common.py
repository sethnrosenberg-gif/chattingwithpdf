"""Helpers shared by discovery channels."""
from __future__ import annotations

import re

from ..extract import classify_location
from ..keywords import relevance
from ..models import Lead, Posting

KEEP = ("nyc", "us_remote", "us_other")
ATS_URL = re.compile(
    r"https?://(?:job-boards|boards)\.greenhouse\.io/[\w.-]+/jobs/\d+|https?://jobs\.lever\.co/[\w.-]+/[0-9a-f-]{36}"
    r"|https?://jobs\.ashbyhq\.com/[\w.-]+/[0-9a-f-]{36}|https?://[\w-]+\.wd\d+\.myworkdayjobs\.com/[^\s\"'<>]+"
    r"|https?://apply\.workable\.com/[\w.-]+/j/\w+|https?://[\w-]+\.bamboohr\.com/careers/\d+",
    re.I,
)


def posting_leads(postings: list[Posting], source: str, company: str | None = None) -> list[Lead]:
    out = []
    for p in postings:
        ok, why = relevance(p.title, p.description)
        if ok and p.loc_bucket in KEEP:
            out.append(Lead(source=source, url=p.url, company=company or p.company, title=p.title,
                            location=p.location, note=why, ats=p.ats, board=p.board))
    return out


def keep_location(loc: str) -> bool:
    return classify_location(loc) in KEEP
