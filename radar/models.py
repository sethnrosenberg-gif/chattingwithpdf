"""Typed records passed between phases."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Posting(BaseModel):
    """One job posting as verified in this run."""

    key: str  # stable id: "<ats>:<board>:<job_id>" or "url:<normalized url>"
    company: str
    title: str
    url: str  # human-facing employer posting page
    apply_url: str | None = None
    ats: str | None = None
    board: str | None = None
    job_id: str | None = None

    location: str = ""
    locations: list[str] = Field(default_factory=list)
    workplace: str = ""  # remote | hybrid | onsite | ""
    loc_bucket: str = "unknown"  # nyc | us_remote | us_other | non_us | unknown

    pay_min: float | None = None
    pay_max: float | None = None
    pay_type: str = "not listed"  # base | OTE | hourly | not listed
    pay_period: str | None = None  # year | hour | month
    pay_currency: str | None = None
    pay_extras: str = ""  # "+ bonus + equity"
    pay_source: str = ""  # which field/regex produced the pay
    pay_display: str = "Not listed"

    years_required: int | None = None
    years_text: str = ""
    jd_required: str = "N"  # Y | N | pref
    posted_date: str | None = None
    closes_date: str | None = None
    description: str = ""  # plain text

    status: str = "unverified"  # open | closed | unverified
    status_evidence: str = ""
    verified_at: str | None = None
    via_aggregator: str | None = None  # set when the only reachable page is an aggregator

    sources: list[str] = Field(default_factory=list)
    segment: str | None = None
    pipeline: bool = False

    # scoring
    relevant: bool = False
    relevance_reason: str = ""
    fit_score: int = 0
    fit_signals: list[str] = Field(default_factory=list)
    hard_exclude_reason: str = ""
    poor_reason: str = ""
    sales_attached: str = "N"
    litigation_accepted: str = ""
    domain_floor: str = ""
    judgment_rationale: str = ""
    bucket: str = ""  # fit | poor | outside | closed | irrelevant

    def dedupe_key(self) -> str:
        from .textutil import norm_company, norm_title

        area = "main" if self.loc_bucket in ("nyc", "us_remote") else self.loc_bucket
        return f"{norm_company(self.company)}|{norm_title(self.title)}|{area}"


class Lead(BaseModel):
    """A candidate from a discovery channel. Not evidence of anything until verified."""

    source: str  # channel name, e.g. "hn_whoishiring"
    url: str
    company: str | None = None
    title: str | None = None
    location: str | None = None
    note: str = ""
    found_at: str | None = None
    ats: str | None = None
    board: str | None = None
