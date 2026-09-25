"""Official job APIs: The Muse (keyless), USAJobs / Adzuna / SerpAPI (skipped without keys)."""
from __future__ import annotations

from .. import config
from ..http import client
from ..keywords import relevance
from ..leads import add_leads
from ..models import Lead
from ..runlog import record_channel
from ..textutil import html_to_text
from .common import keep_location

MUSE = "https://www.themuse.com/api/public/jobs"
MUSE_CATEGORIES = ["Legal", "Compliance", "Finance", "Accounting and Finance", "Data and Analytics", "Government and Public Policy"]
MUSE_LOCATIONS = ["New York, NY", "Flexible / Remote"]
MUSE_MAX_PAGES = 10
USAJOBS_ORGS = "SE00,CT00,TR93,FQ00,FD00,TR00"  # SEC, CFTC, OCC, CFPB, FDIC, Treasury


def _muse(stats: dict) -> list[Lead]:
    leads = []
    key = config.env("MUSE_API_KEY")
    for cat in MUSE_CATEGORIES:
        for loc in MUSE_LOCATIONS:
            for page in range(MUSE_MAX_PAGES):
                params = {"category": cat, "location": loc, "page": page}
                if key:
                    params["api_key"] = key
                r = client().get(MUSE, params=params)
                stats["queried"] += 1
                if not r.ok:
                    stats["failures"].append(f"muse {cat}/{loc}: {r.describe()}")
                    break
                d = r.json()
                for j in d.get("results", []):
                    locs = [l.get("name", "") for l in j.get("locations", [])]
                    desc = html_to_text(j.get("contents", ""))
                    ok, why = relevance(j.get("name", ""), desc)
                    if ok and any(keep_location(l) for l in locs):
                        leads.append(Lead(source="official_apis:themuse", url=(j.get("refs") or {}).get("landing_page", ""),
                                          company=(j.get("company") or {}).get("name"), title=j.get("name"),
                                          location="; ".join(locs), note=f"The Muse ({cat}); {why}"))
                if page + 1 >= d.get("page_count", 0):
                    break
    return leads


def _usajobs(stats: dict) -> list[Lead]:
    key, email = config.env("USAJOBS_API_KEY"), config.env("USAJOBS_EMAIL")
    if not (key and email):
        stats["skipped"].append("usajobs: no USAJOBS_API_KEY/USAJOBS_EMAIL in .env (note: data.usajobs.gov robots.txt is "
                                "'Disallow: /', so also add it to RADAR_ROBOTS_EXEMPT_HOSTS when you add a key)")
        return []
    leads = []
    for kw in ("attorney", "counsel", "policy"):
        r = client().get("https://data.usajobs.gov/api/search", headers={"Authorization-Key": key, "User-Agent": email},
                         params={"Keyword": kw, "Organization": USAJOBS_ORGS, "LocationName": "New York, New York", "ResultsPerPage": 250})
        stats["queried"] += 1
        if not r.ok:
            stats["failures"].append(f"usajobs {kw}: {r.describe()}")
            continue
        for item in r.json().get("SearchResult", {}).get("SearchResultItems", []):
            d = item.get("MatchedObjectDescriptor", {})
            leads.append(Lead(source="official_apis:usajobs", url=d.get("PositionURI", ""), company=d.get("OrganizationName"),
                              title=d.get("PositionTitle"), location=d.get("PositionLocationDisplay"), note=kw))
    return leads


def _adzuna(stats: dict) -> list[Lead]:
    app, key = config.env("ADZUNA_APP_ID"), config.env("ADZUNA_APP_KEY")
    if not (app and key):
        stats["skipped"].append("adzuna: no ADZUNA_APP_ID/ADZUNA_APP_KEY in .env")
        return []
    leads = []
    for what in ("legal analyst", "regulatory counsel", "product counsel", "litigation finance", "policy counsel"):
        r = client().get("https://api.adzuna.com/v1/api/jobs/us/search/1",
                         params={"app_id": app, "app_key": key, "what": what, "where": "New York", "results_per_page": 50})
        stats["queried"] += 1
        if r.ok:
            for j in r.json().get("results", []):
                if relevance(j.get("title", ""), j.get("description", ""))[0]:
                    leads.append(Lead(source="official_apis:adzuna", url=j.get("redirect_url", ""),
                                      company=(j.get("company") or {}).get("display_name"), title=j.get("title"),
                                      location=(j.get("location") or {}).get("display_name"), note=what))
    return leads


def _serpapi(stats: dict) -> list[Lead]:
    key = config.env("SERPAPI_KEY")
    if not key:
        stats["skipped"].append("serpapi: no SERPAPI_KEY in .env")
        return []
    leads = []
    for q in ("legal analyst New York", "regulatory counsel fintech New York", "litigation finance underwriting"):
        r = client().get("https://serpapi.com/search.json", params={"engine": "google_jobs", "q": q, "api_key": key})
        stats["queried"] += 1
        if r.ok:
            for j in r.json().get("jobs_results", []):
                link = next((o.get("link") for o in j.get("apply_options", []) if o.get("link")), j.get("share_link", ""))
                leads.append(Lead(source="official_apis:serpapi", url=link, company=j.get("company_name"),
                                  title=j.get("title"), location=j.get("location"), note=q))
    return leads


def run() -> dict:
    stats = {"queried": 0, "failures": [], "skipped": []}
    leads = _muse(stats) + _usajobs(stats) + _adzuna(stats) + _serpapi(stats)
    written = add_leads([l for l in leads if l.url])
    record_channel("discover:official_apis", queried=stats["queried"], candidates=len([l for l in leads if l.url]),
                   failures=stats["failures"], skipped=stats["skipped"], notes=f"The Muse leads {sum(l.source.endswith('themuse') for l in leads)}")
    return {**stats, "leads": written}
