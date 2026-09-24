"""Verify a single posting URL on the employer's own system, whatever ATS it uses."""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from .ats import ashby, greenhouse, html as htmlats, lever, nyag, workday
from .http import client
from .models import Posting
from .textutil import html_to_text, jsonld_jobposting, norm_title

AGGREGATOR_HOSTS = (
    "jobleads.com", "politicalriskjobs.com", "builtin.com", "builtinnyc.com", "legal.io", "goinhouse.com",
    "ziprecruiter.com", "talents.vaia.com", "jobright.ai", "theladders.com", "startup.jobs", "justia.jobs",
    "themuse.com", "simplyhired", "glassdoor.com", "indeed.com", "linkedin.com", "sonara.ai",
)


def is_aggregator(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return any(host.endswith(h) or h in host for h in AGGREGATOR_HOSTS)


@dataclass
class Outcome:
    status: str  # open | closed | unverified
    posting: Posting | None
    evidence: str
    method: str


def _js_id(url: str) -> str | None:
    m = re.search(r"janestreet\.com/join-jane-street/(?:position|apply)/(\d+)", url)
    return m.group(1) if m else None


_js_cache: list[Posting] | None = None


def janestreet_jobs() -> list[Posting]:
    global _js_cache
    if _js_cache is None:
        st, ps = htmlats.janestreet_feed()
        _js_cache = ps if st == "ok" else []
    return _js_cache


def verify_url(url: str, company: str, source: str = "verify") -> Outcome:
    """Returns open/closed with evidence from a fetch made now, or unverified with the reason."""
    try:
        if jid := _js_id(url):
            for p in janestreet_jobs():
                if p.job_id == jid:
                    p.sources = [source]
                    return Outcome("open", p, p.status_evidence, "janestreet feed")
            gh = greenhouse.verify("janestreet", jid, company, source)
            if gh:
                return Outcome("open", gh, gh.status_evidence, "greenhouse")
            return Outcome("closed", None, f"Jane Street jobs feed no longer lists position {jid}, and Greenhouse returns 404 for it", "janestreet feed")

        if (g := greenhouse.parse_url(url)) and g[0]:
            p = greenhouse.verify(g[0], g[1], company, source)
            if p:
                return Outcome("open", p, p.status_evidence, "greenhouse api")
            return Outcome("closed", None, f"Greenhouse API returns 404 for job {g[1]} on board '{g[0]}'", "greenhouse api")

        if a := ashby.parse_url(url):
            p = ashby.verify(a[0], a[1], company, source)
            if p:
                if urlsplit(url).netloc.endswith("harvey.ai"):
                    p.url = url  # keep the employer's own career-site link
                return Outcome("open", p, p.status_evidence, "ashby api")
            return Outcome("closed", None, f"Ashby board '{a[0]}' no longer lists job {a[1]}", "ashby api")

        if l := lever.parse_url(url):
            p = lever.verify(l[0], l[1], company, source)
            if p:
                return Outcome("open", p, p.status_evidence, "lever api")
            return Outcome("closed", None, f"Lever API returns 404 for {l[1]}", "lever api")

        if workday.parse_url(url) and "/job/" in url:
            p = workday.verify_url(url, company, source)
            if p and p.status == "open":
                return Outcome("open", p, p.status_evidence, "workday cxs")
            if p:
                return Outcome("closed", p, p.status_evidence, "workday cxs")
            return Outcome("closed", None, "Workday detail endpoint returns 404 / not posted", "workday cxs")

        if htmlats.is_rmk(url):
            p = htmlats.rmk_verify(url, company, source)
            if p:
                return Outcome("open", p, p.status_evidence, "successfactors page")
            return Outcome("closed", None, "SuccessFactors job page redirects to its error page (job removed)", "successfactors page")

        if "ag.ny.gov" in url:
            p = nyag.verify(url, source)
            if p and p.status == "open":
                return Outcome("open", p, p.status_evidence, "ag.ny.gov listing + pdf")
            if p:
                return Outcome("closed", p, p.status_evidence, "ag.ny.gov listing")
            return Outcome("closed", None, "Reference number no longer appears on any ag.ny.gov job-postings page", "ag.ny.gov listing")

        # generic employer page: JSON-LD JobPosting or a clear closed message
        r = client().get(url)
        if r.blocked:
            return Outcome("unverified", None, f"Employer page blocked: {r.describe()}", "page")
        if r.status in (404, 410):
            return Outcome("closed", None, f"Page returns HTTP {r.status}", "page")
        if not r.ok:
            return Outcome("unverified", None, f"Page fetch failed: {r.describe()}", "page")
        try:
            p = htmlats.jsonld_verify(url, company, source, html=r.text)
        except LookupError:
            return Outcome("unverified", None, "Page loaded but carries no JobPosting data or closed notice", "page")
        if p is None:
            return Outcome("closed", None, "Page says the posting is closed / past validThrough", "jsonld page")
        if is_aggregator(url):
            p.via_aggregator = urlsplit(url).netloc
        return Outcome("open", p, p.status_evidence, "jsonld page")
    except RuntimeError as e:
        return Outcome("unverified", None, str(e), "error")


# ------------------------------------------------------------------- board search
def point72_urls() -> list[str]:
    r = client().get("https://careers.point72.com/CSSitemap")
    if not r.ok:
        return []
    urls = re.findall(r"<loc>([^<]*CSJobDetail[^<]*)</loc>", r.text)
    return [htmllib.unescape(unquote(u)) for u in urls]


def point72_title(url: str) -> str:
    m = re.search(r"jobName=([^&]+)", url)
    return m.group(1).replace("-", " ") if m else url


def search_board(method: str, target: str, company: str, title_rx: str, loc_rx: str = "", source: str = "watch") -> tuple[str, list[Posting]]:
    """Find postings on one employer board whose title matches. Returns (status, open postings)."""
    trx = re.compile(title_rx, re.I)
    lrx = re.compile(loc_rx, re.I) if loc_rx else None
    found: list[Posting] = []
    if method == "greenhouse":
        st, ps = greenhouse.pull(target, company, source)
        found = [greenhouse.enrich_pay(p) for p in ps if trx.search(p.title)]
    elif method == "ashby":
        st, ps = ashby.pull(target, company, source)
        found = [p for p in ps if trx.search(p.title)]
    elif method == "lever":
        st, ps = lever.pull(target, company, source)
        found = [p for p in ps if trx.search(p.title)]
    elif method == "janestreet":
        ps = janestreet_jobs()
        st = "ok" if ps else "feed unavailable"
        found = [p for p in ps if trx.search(p.title)]
    elif method == "workday":
        spec = workday.spec_from_slug(target)
        words = re.sub(r"[^a-z ]", " ", title_rx.split("|")[0].replace(".*", " ")).strip()
        st, jobs = workday.list_jobs(spec, search_text=words, max_pages=5)
        for j in jobs:
            if trx.search(j.get("title", "")):
                p = workday.detail(spec, j["externalPath"], company, source)
                if p:
                    found.append(p)
    elif method == "point72":
        urls = point72_urls()
        st = "ok" if urls else "sitemap unavailable"
        for u in urls:
            if trx.search(point72_title(u)):
                o = verify_url(u, company, source)
                if o.posting and o.status == "open":
                    found.append(o.posting)
    elif method == "page":
        r = client().get(target)
        if not r.ok:
            return r.describe(), []
        st = "ok"
        text = html_to_text(r.text)
        if trx.search(text):
            m = trx.search(text)
            ctx = re.sub(r"\s+", " ", text[max(0, m.start() - 80): m.end() + 160])
            jp = jsonld_jobposting(r.text)
            p = htmlats.jsonld_verify(target, company, source, html=r.text) if jp else None
            if p is None:
                from .ats.base import build_posting
                from .extract import classify_location

                nxt = [l.strip(" -|") for l in text[m.end(): m.end() + 120].split("\n") if l.strip(" -|")]
                loc = nxt[0] if nxt and len(nxt[0]) < 50 and classify_location(nxt[0]) != "unknown" else ""
                line = text[text.rfind("\n", 0, m.start()) + 1: m.end()].strip(" -|")
                p = build_posting(ats="page", board=urlsplit(target).netloc, job_id=None, company=company,
                                  title=line or m.group(0), url=target, description_text=ctx, locations=[loc],
                                  source=source, evidence=f"Employer careers page lists “{line or m.group(0)}”" + (f" ({loc})" if loc else "") + " on this run")
            found.append(p)
    else:
        return "no employer board known", []
    if lrx:
        found = [p for p in found if lrx.search(p.location)]
    return st, [p for p in found if p.status == "open"]


def find_repost(p_title: str, company: str, method: str, target: str) -> Posting | None:
    """Same title reposted under a new id on the same board?"""
    want = norm_title(p_title)
    words = [w for w in want.split() if len(w) > 3][:4]
    if not words:
        return None
    rx = ".*".join(re.escape(w) for w in words)
    st, found = search_board(method, target, company, rx)
    for p in found:
        if norm_title(p.title) == want or all(w in norm_title(p.title) for w in words):
            return p
    return None
