"""Workday CXS endpoints (the JSON the Workday careers SPA itself calls)."""
from __future__ import annotations

import re

from ..http import client
from ..models import Posting
from .base import build_posting

URL_RX = re.compile(
    r"https?://(?P<tenant>[\w-]+)\.(?P<wd>wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?(?P<site>[\w-]+)(?P<path>/job/[^?#]+)?",
)


def parse_url(url: str) -> dict | None:
    m = URL_RX.search(url)
    if not m or m.group("site") in ("wday",):
        return None
    return m.groupdict()


def spec_from_slug(slug: str) -> dict | None:
    """Registry slugs are 'tenant|wdN|site'."""
    parts = slug.split("|")
    if len(parts) != 3:
        return None
    return {"tenant": parts[0], "wd": parts[1], "site": parts[2]}


def _base(spec: dict) -> str:
    return f"https://{spec['tenant']}.{spec['wd']}.myworkdayjobs.com/wday/cxs/{spec['tenant']}/{spec['site']}"


def public_url(spec: dict, path: str) -> str:
    return f"https://{spec['tenant']}.{spec['wd']}.myworkdayjobs.com/{spec['site']}{path}"


def list_jobs(spec: dict, search_text: str = "", max_pages: int = 200) -> tuple[str, list[dict]]:
    out: list[dict] = []
    total = None
    offset = 0
    for _ in range(max_pages):
        r = client().post_json(f"{_base(spec)}/jobs", {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": search_text})
        if not r.ok:
            return (r.describe() if not out else f"partial ({r.describe()})"), out
        d = r.json()
        if total is None:
            total = d.get("total") or 0
        page = d.get("jobPostings") or []
        out.extend(page)
        offset += 20
        if not page or offset >= (total or 0):
            break
    return "ok", out


def light_postings(spec: dict, company: str, jobs: list[dict], source: str) -> list[Posting]:
    res = []
    for j in jobs:
        path = j.get("externalPath") or ""
        jid = (j.get("bulletFields") or [path.rsplit("_", 1)[-1]])[0]
        res.append(build_posting(
            ats="workday", board=f"{spec['tenant']}|{spec['wd']}|{spec['site']}", job_id=jid, company=company,
            title=j.get("title", ""), url=public_url(spec, path), description_text="",
            locations=[j.get("locationsText") or ""], posted=None, source=source, status="listed",
            evidence=f"Workday list endpoint shows {jid} (postedOn: {j.get('postedOn')})",
        ).model_copy(update={"apply_url": path}))
    return res


def detail(spec: dict, path: str, company: str, source: str = "verify") -> Posting | None:
    r = client().get(f"{_base(spec)}{path}")
    if r.status in (404, 410):
        return None
    if not r.ok:
        raise RuntimeError(f"workday {spec['tenant']}{path}: {r.describe()}")
    d = r.json()
    info = d.get("jobPostingInfo") or {}
    if not info or info.get("posted") is False:
        return None
    locs = [info.get("location") or ""] + list(info.get("additionalLocations") or [])
    country = ((info.get("country") or {}).get("descriptor") or "")
    country = "US" if "United States" in country else (country or None)
    jid = info.get("jobReqId") or path.rsplit("_", 1)[-1]
    p = build_posting(
        ats="workday", board=f"{spec['tenant']}|{spec['wd']}|{spec['site']}", job_id=jid, company=company,
        title=info.get("title", ""), url=info.get("externalUrl") or public_url(spec, path),
        description_html=info.get("jobDescription"), locations=locs, country=country if len(locs) == 1 else None,
        remote_flag=bool(re.search(r"remote", (info.get("remoteType") or "") + " " + " ".join(locs), re.I)),
        posted=info.get("startDate"), closes=info.get("endDate"), source=source,
        apply_url=(info.get("externalUrl") or public_url(spec, path)) + "/apply",
        evidence=f"Workday detail endpoint returned {jid} with posted=true, canApply={info.get('canApply')} on this run",
    )
    if info.get("canApply") is False:
        p.status = "closed"
        p.status_evidence = "Workday shows the posting but canApply=false"
    return p


def verify_url(url: str, company: str, source: str = "verify") -> Posting | None:
    m = parse_url(url)
    if not m or not m.get("path"):
        raise RuntimeError(f"not a Workday job URL: {url}")
    return detail(m, m["path"], company, source)
