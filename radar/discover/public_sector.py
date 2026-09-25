"""Public-sector portals: NYDFS, NY AG, NY State jobs, NY Fed, FINRA.

Each portal's listing is found by following links from its careers page every run, so
nothing here depends on posting IDs. Blocks (ag.ny.gov returns 403 to this client) are logged.
"""
from __future__ import annotations

import html as htmllib
import re
from urllib.parse import urljoin

from ..ats import workday
from ..ats.nyag import all_listings
from ..http import client
from ..keywords import relevance
from ..leads import add_leads
from ..models import Lead
from ..runlog import record_channel
from ..textutil import html_to_text
from .common import ATS_URL, keep_location, posting_leads

PUBLIC_TITLES = re.compile(r"attorney|counsel|policy|examiner|analyst|investigat|regulat|economist|specialist", re.I)


def _links(html: str, base: str) -> list[tuple[str, str]]:
    return [(urljoin(base, htmllib.unescape(h)), htmllib.unescape(re.sub(r"<[^>]+>|\s+", " ", t)).strip())
            for h, t in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, re.S)]


def _nydfs(stats) -> list[Lead]:
    r = client().get("https://www.dfs.ny.gov/careers")
    stats["queried"] += 1
    if not r.ok:
        stats["skipped"].append(f"nydfs careers: {r.describe()}")
        return []
    # the careers page links each posting (usually a PDF) directly under /careers_with_dfs/
    postings = {u.strip(): html_to_text(t) for u, t in _links(r.text, r.final_url or r.url)
                if re.search(r"/careers_with_dfs/.+", u, re.I)}
    leads = [Lead(source="public_sector:nydfs", url=u, company="NY Department of Financial Services", title=t,
                  location="", note="NYDFS careers page; location and pay are in the posting PDF")
             for u, t in postings.items() if PUBLIC_TITLES.search(t) and relevance(t, "financial services regulator")[0]]
    stats["notes"].append(f"nydfs postings listed {len(postings)}, relevant {len(leads)}")
    return leads


def _nyag(stats) -> list[Lead]:
    statuses, rows = all_listings()
    stats["queried"] += len(statuses)
    if not rows:
        stats["skipped"].append("ag.ny.gov: " + "; ".join(f"{k} {v}" for k, v in statuses.items()))
        return []
    return [Lead(source="public_sector:nyag", url=e["pdf"], company="NY Attorney General", title=e["title"],
                 location=e["location"], note=f"{e['bureau']}; deadline {e['deadline_text']}")
            for e in rows if relevance(e["title"], "attorney")[0] and keep_location(e["location"])]


def _statejobs(stats) -> list[Lead]:
    r = client().get("https://statejobs.ny.gov/public/vacancyTable.cfm")
    stats["queried"] += 1
    if not r.ok:
        stats["skipped"].append(f"statejobs.ny.gov: {r.describe()}")
        return []
    leads = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
        cells = [html_to_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        links = _links(row, r.url)
        if len(cells) < 3 or not links:
            continue
        text = " | ".join(cells)
        title = links[0][1] or cells[0]
        if (PUBLIC_TITLES.search(title) and re.search(r"financial services|attorney general|tax|comptroller|law|securit", text, re.I)
                and re.search(r"new york|manhattan|brooklyn|bronx|queens|kings|richmond", text, re.I)
                and relevance(title, text + " financial regulator")[0]):
            agency = next((c for c in cells if re.search(r"department|office|attorney general|division|commission|authority|law", c, re.I)
                           and c != title), "NY State")
            if re.search(r"attorney general|OAG", title + " " + agency, re.I):
                agency = "NY Attorney General"
            elif re.search(r"financial services", agency, re.I):
                agency = "NY Department of Financial Services"
            leads.append(Lead(source="public_sector:statejobs", url=links[0][0], company=agency,
                              title=title, location="New York, NY", note=text[:200]))
    stats["notes"].append(f"statejobs leads {len(leads)}")
    return leads


def _workday_portal(name: str, careers: str, stats) -> list[Lead]:
    r = client().get(careers)
    stats["queried"] += 1
    if not r.ok:
        stats["skipped"].append(f"{name} careers page: {r.describe()}")
        return []
    spec = None
    for u in re.findall(r"https?://[\w-]+\.wd\d+\.myworkdayjobs\.com/[^\s\"'<>]+", r.text):
        spec = workday.parse_url(u)
        if spec:
            break
    if not spec:
        other = ATS_URL.search(r.text)
        stats["skipped"].append(f"{name}: no Workday link on {careers}" + (f" (found {other.group(0)})" if other else ""))
        return []
    status, jobs = workday.list_jobs(spec)
    stats["queried"] += len(jobs) // 20 + 1
    stats["notes"].append(f"{name}: workday {spec['tenant']}|{spec['wd']}|{spec['site']} ({len(jobs)} jobs, {status})")
    light = workday.light_postings(spec, name, jobs, f"public_sector:{name}")
    return [l for l in posting_leads(light, f"public_sector:{name.lower().replace(' ', '_')}", name)]


def run() -> dict:
    stats = {"queried": 0, "failures": [], "skipped": [], "notes": []}
    leads = []
    for fn in (_nydfs, _nyag, _statejobs):
        try:
            leads += fn(stats)
        except Exception as e:  # one broken portal shouldn't stop the others
            stats["failures"].append(f"{fn.__name__}: {type(e).__name__}: {e}")
    for name, url in (("NY Fed", "https://www.newyorkfed.org/careers"), ("FINRA", "https://www.finra.org/careers")):
        try:
            leads += _workday_portal(name, url, stats)
        except Exception as e:
            stats["failures"].append(f"{name}: {type(e).__name__}: {e}")
    written = add_leads(leads)
    record_channel("discover:public_sector", queried=stats["queried"], candidates=len(leads), failures=stats["failures"],
                   skipped=stats["skipped"], notes="; ".join(stats["notes"]))
    return {**stats, "leads": written}
