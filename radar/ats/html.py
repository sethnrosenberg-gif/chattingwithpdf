"""Verifiers for employer career pages that aren't a JSON ATS API.

- SuccessFactors Recruiting Marketing ("jobs2web"/RMK) sites: Burford, Fitch
- Any page carrying schema.org JobPosting JSON-LD: Point72, D. E. Shaw, Citadel, Harvey...
- Jane Street's own jobs feed (janestreet.com/jobs/main.json)
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import unquote, urlsplit

from selectolax.parser import HTMLParser

from ..http import client
from ..models import Posting
from ..textutil import html_to_text, jsonld_jobposting
from .base import build_posting, pay_from_jsonld, pay_from_range

CLOSED_PHRASES = re.compile(
    r"no longer (available|accepting|open|active)|position (has been )?(filled|closed)|job (is )?(closed|expired|not found)"
    r"|this (job|posting|position|requisition) (has )?(expired|closed|been removed)|page not found|could not be found"
    r"|isn't available|is not available anymore|we couldn.t find",
    re.I,
)


# ------------------------------------------------------------------ SuccessFactors
RMK_HOSTS = {"careers.burfordcapital.com": "Burford Capital", "careers.fitch.group": "Fitch Group"}


def is_rmk(url: str) -> bool:
    return urlsplit(url).netloc.lower() in RMK_HOSTS


def rmk_sitemap(host: str) -> tuple[str, list[str]]:
    r = client().get(f"https://{host}/sitemap.xml")
    if not r.ok:
        return r.describe(), []
    return "ok", re.findall(r"<loc>([^<]+/job/[^<]+)</loc>", r.text)


def rmk_title_from_url(url: str) -> str:
    """'/job/New-York-Vice-President,-Commercial-Underwriting-NY-10017/1331385600/' -> readable slug."""
    seg = unquote(urlsplit(url).path.split("/job/", 1)[-1].rsplit("/", 2)[0])
    return seg.replace("-", " ")


def rmk_verify(url: str, company: str | None = None, source: str = "verify") -> Posting | None:
    r = client().get(url)
    host = urlsplit(url).netloc.lower()
    company = company or RMK_HOSTS.get(host, host)
    if r.blocked:
        raise RuntimeError(r.describe())
    if r.status in (404, 410) or any("errorpage" in h for h in r.redirects) or (r.status in (301, 302) and "errorpage" in r.headers.get("location", "")):
        return None
    if not r.ok:
        raise RuntimeError(f"{url}: {r.describe()}")
    tree = HTMLParser(r.text)
    t = tree.css_first('[itemprop="title"]')
    if not t:
        return None
    desc = tree.css_first('[itemprop="description"]')

    def meta(prop: str) -> str:
        n = tree.css_first(f'[itemprop="{prop}"]')
        return (n.attributes.get("content") or n.text(strip=True)) if n else ""

    loc = ", ".join(x for x in (meta("addressLocality"), meta("addressRegion")) if x)
    country = meta("addressCountry") or None
    jid = url.rstrip("/").rsplit("/", 1)[-1]
    return build_posting(
        ats="successfactors", board=host, job_id=jid, company=company, title=t.text(strip=True), url=url,
        description_html=desc.html if desc else "", locations=[loc], country=country,
        posted=meta("datePosted"), source=source, apply_url=url,
        evidence="Employer SuccessFactors job page loaded with title and description on this run",
    )


# ------------------------------------------------------------------ JSON-LD pages
def _jsonld_locations(jp: dict) -> tuple[list[str], str | None]:
    locs, country = [], None
    jl = jp.get("jobLocation")
    items = jl if isinstance(jl, list) else [jl] if jl else []
    for it in items:
        addr = (it or {}).get("address") or {}
        if isinstance(addr, str):
            locs.append(addr)
            continue
        parts = [addr.get("addressLocality"), addr.get("addressRegion")]
        c = addr.get("addressCountry")
        if isinstance(c, dict):
            c = c.get("name")
        country = country or c
        locs.append(", ".join(p for p in (*parts, c) if p))
    if str(jp.get("jobLocationType", "")).upper() == "TELECOMMUTE":
        req = jp.get("applicantLocationRequirements") or {}
        reqs = req if isinstance(req, list) else [req]
        names = [r.get("name", "") for r in reqs if isinstance(r, dict)]
        locs.append("Remote" + (f" ({', '.join(n for n in names if n)})" if any(names) else ""))
    return locs, country


def jsonld_verify(url: str, company: str | None = None, source: str = "verify", html: str | None = None) -> Posting | None:
    if html is None:
        r = client().get(url)
        if r.blocked:
            raise RuntimeError(r.describe())
        if r.status in (404, 410):
            return None
        if not r.ok:
            raise RuntimeError(f"{url}: {r.describe()}")
        html = r.text
    jp = jsonld_jobposting(html)
    if not jp:
        if CLOSED_PHRASES.search(html_to_text(html)[:5000]):
            return None
        raise LookupError("no JobPosting JSON-LD on page")
    valid = jp.get("validThrough")
    if valid:
        try:
            if dt.date.fromisoformat(str(valid)[:10]) < dt.date.today():
                return None
        except ValueError:
            pass
    org = jp.get("hiringOrganization") or {}
    org_name = org.get("name") if isinstance(org, dict) else None
    locs, country = _jsonld_locations(jp)
    if not any(l.strip(" ,") for l in locs):
        locs = [location_near_title(html, jp.get("title") or jp.get("name") or "")]
    desc = jp.get("description") or ""
    for k in ("responsibilities", "qualifications", "skills", "educationRequirements", "experienceRequirements"):
        v = jp.get(k)
        if isinstance(v, str) and v:
            desc += f"\n<p>{v}</p>"
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    jid = str((jp.get("identifier") or {}).get("value") or "") if isinstance(jp.get("identifier"), dict) else ""
    return build_posting(
        ats="jsonld", board=host, job_id=jid or None, company=company or org_name or host,
        title=jp.get("title") or jp.get("name") or "", url=url, description_html=desc, locations=locs,
        country=country if len(locs) <= 1 else None, remote_flag=str(jp.get("jobLocationType", "")).upper() == "TELECOMMUTE",
        pay=pay_from_jsonld(jp), posted=jp.get("datePosted"), closes=valid, source=source, apply_url=url,
        evidence="Employer page served schema.org JobPosting on this run" + (f" (validThrough {valid})" if valid else ""),
    )


def location_near_title(html: str, title: str) -> str:
    """D. E. Shaw-style pages print 'Title / Team / New York' but leave JSON-LD address blank."""
    from ..extract import classify_location

    text = html_to_text(html)
    i = text.find(title) if title else -1
    window = text[i + len(title): i + len(title) + 300] if i >= 0 else text[:1500]
    for line in (l.strip(" -|") for l in window.split("\n")):
        if line and len(line) < 60 and classify_location(line) != "unknown":
            return line
    return ""


# --------------------------------------------------------------------- Jane Street
JS_FEED = "https://www.janestreet.com/jobs/main.json"
JS_CITY = {"NYC": "New York, NY", "LDN": "London", "HKG": "Hong Kong", "SGP": "Singapore", "AMS": "Amsterdam", "CHI": "Chicago"}


def janestreet_feed(source: str = "board:janestreet") -> tuple[str, list[Posting]]:
    r = client().get(JS_FEED)
    if not r.ok:
        return r.describe(), []
    out = []
    for j in r.json():
        lo = float(str(j["min_salary"]).replace(",", "")) if j.get("min_salary") else None
        hi = float(str(j["max_salary"]).replace(",", "")) if j.get("max_salary") else None
        html = "".join(str(j.get(k) or "") for k in ("overview", "team_description", "role", "requirements", "about_you"))
        out.append(build_posting(
            ats="janestreet", board="janestreet", job_id=str(j["id"]), company="Jane Street",
            title=j.get("position", "").strip(), url=f"https://www.janestreet.com/join-jane-street/position/{j['id']}/",
            description_html=html, locations=[JS_CITY.get(j.get("city"), j.get("city") or "")],
            pay=pay_from_range(lo, hi, source="janestreet:feed") if lo else None, source=source,
            evidence=f"Jane Street jobs feed lists position {j['id']} on this run",
        ))
    return "ok", out
