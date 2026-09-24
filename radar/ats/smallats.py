"""Workable, Recruitee, BambooHR and SmartRecruiters adapters (smaller employers)."""
from __future__ import annotations

from ..http import client
from ..models import Posting
from .base import build_posting, pay_from_range

# ------------------------------------------------------------------ SmartRecruiters
# api.smartrecruiters.com/robots.txt disallows every agent except LinkedInBot, so the
# client refuses these calls and the run log records the block.
SR_API = "https://api.smartrecruiters.com/v1/companies"


def sr_probe(slug: str) -> tuple[bool, int]:
    r = client().get(f"{SR_API}/{slug}/postings")
    if r.ok:
        d = r.json()
        return d.get("totalFound", 0) > 0, d.get("totalFound", 0)
    return False, 0


def sr_pull(slug: str, company: str, source: str = "board:smartrecruiters") -> tuple[str, list[Posting]]:
    r = client().get(f"{SR_API}/{slug}/postings", params={"limit": 100})
    if not r.ok:
        return r.describe(), []
    out = []
    for j in r.json().get("content", []):
        loc = j.get("location") or {}
        out.append(build_posting(
            ats="smartrecruiters", board=slug, job_id=j.get("id"), company=company, title=j.get("name", ""),
            url=f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}", description_text="",
            locations=[", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)],
            remote_flag=loc.get("remote"), country=(loc.get("country") or "").upper() or None,
            posted=j.get("releasedDate"), source=source, status="listed",
        ))
    return "ok", out


# ------------------------------------------------------------------------ Workable
WK = "https://apply.workable.com/api"


def wk_probe(slug: str) -> tuple[bool, int]:
    r = client().post_json(f"{WK}/v3/accounts/{slug}/jobs", {"query": "", "location": [], "department": [], "worktype": [], "remote": []})
    if r.ok:
        d = r.json()
        return True, d.get("total", len(d.get("results", [])))
    return False, 0


def wk_pull(slug: str, company: str, source: str = "board:workable") -> tuple[str, list[Posting]]:
    results, token = [], None
    for _ in range(20):
        body = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}
        if token:
            body["token"] = token
        r = client().post_json(f"{WK}/v3/accounts/{slug}/jobs", body)
        if not r.ok:
            return r.describe(), []
        d = r.json()
        results.extend(d.get("results", []))
        token = d.get("nextPage")
        if not token:
            break
    out = []
    for j in results:
        loc = j.get("location") or {}
        locs = [", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)]
        for l in j.get("locations") or []:
            locs.append(", ".join(x for x in (l.get("city"), l.get("region"), l.get("country")) if x))
        sc = j.get("shortcode")
        out.append(build_posting(
            ats="workable", board=slug, job_id=sc, company=company, title=j.get("title", ""),
            url=f"https://apply.workable.com/{slug}/j/{sc}/", description_text="", locations=locs,
            remote_flag=bool(j.get("remote")), posted=j.get("published"), source=source, status="listed",
        ))
    return "ok", out


def wk_detail(slug: str, shortcode: str, company: str, source: str = "verify") -> Posting | None:
    r = client().get(f"{WK}/v2/accounts/{slug}/jobs/{shortcode}")
    if r.status == 404:
        return None
    if not r.ok:
        raise RuntimeError(f"workable {slug}/{shortcode}: {r.describe()}")
    j = r.json()
    loc = j.get("location") or {}
    html = "\n".join(j.get(k) or "" for k in ("description", "requirements", "benefits"))
    sal = j.get("salary") or {}
    pay = pay_from_range(sal.get("salary_from"), sal.get("salary_to"), source="workable:salary",
                         currency=sal.get("salary_currency") or "USD") if sal.get("salary_from") else None
    p = build_posting(
        ats="workable", board=slug, job_id=shortcode, company=company, title=j.get("title", ""),
        url=f"https://apply.workable.com/{slug}/j/{shortcode}/", description_html=html,
        locations=[", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)],
        remote_flag=bool(j.get("remote")), pay=pay, posted=j.get("published"), source=source,
        evidence=f"Workable API returned job {shortcode} on this run",
    )
    return p


# ----------------------------------------------------------------------- Recruitee
def rc_probe(slug: str) -> tuple[bool, int]:
    r = client().get(f"https://{slug}.recruitee.com/api/offers/")
    if r.ok:
        try:
            return True, len(r.json().get("offers", []))
        except ValueError:
            return False, 0
    return False, 0


def rc_pull(slug: str, company: str, source: str = "board:recruitee") -> tuple[str, list[Posting]]:
    r = client().get(f"https://{slug}.recruitee.com/api/offers/")
    if not r.ok:
        return r.describe(), []
    out = []
    for j in r.json().get("offers", []):
        if j.get("status") not in (None, "published"):
            continue
        sal = j.get("salary") or {}
        period = (sal.get("period") or "year").lower()
        pay = pay_from_range(sal.get("min"), sal.get("max"), period="hour" if "hour" in period else "year",
                             source="recruitee:salary", currency=sal.get("currency") or "USD") if sal.get("min") else None
        out.append(build_posting(
            ats="recruitee", board=slug, job_id=str(j.get("id")), company=company, title=j.get("title", ""),
            url=j.get("careers_url") or f"https://{slug}.recruitee.com/o/{j.get('slug')}",
            description_html=(j.get("description") or "") + (j.get("requirements") or ""),
            locations=[j.get("location") or ""], remote_flag=bool(j.get("remote")), country=j.get("country_code"),
            pay=pay, posted=j.get("published_at"), source=source,
            evidence="Recruitee API lists the offer as published on this run",
        ))
    return "ok", out


# ------------------------------------------------------------------------ BambooHR
def bb_probe(slug: str) -> tuple[bool, int]:
    r = client().get(f"https://{slug}.bamboohr.com/careers/list")
    if r.ok and "json" in r.headers.get("content-type", ""):
        try:
            return True, len(r.json().get("result", []))
        except ValueError:
            return False, 0
    return False, 0


def bb_pull(slug: str, company: str, source: str = "board:bamboohr") -> tuple[str, list[Posting]]:
    r = client().get(f"https://{slug}.bamboohr.com/careers/list")
    if not r.ok:
        return r.describe(), []
    out = []
    for j in r.json().get("result", []):
        loc = j.get("location") or {}
        locs = [", ".join(x for x in (loc.get("city"), loc.get("state")) if x)]
        out.append(build_posting(
            ats="bamboohr", board=slug, job_id=str(j.get("id")), company=company, title=j.get("jobOpeningName", ""),
            url=f"https://{slug}.bamboohr.com/careers/{j.get('id')}", description_text="", locations=locs,
            remote_flag=bool(j.get("isRemote")), source=source, status="listed",
        ))
    return "ok", out


def bb_detail(slug: str, job_id: str, company: str, source: str = "verify") -> Posting | None:
    r = client().get(f"https://{slug}.bamboohr.com/careers/{job_id}/detail")
    if r.status == 404:
        return None
    if not r.ok:
        raise RuntimeError(f"bamboohr {slug}/{job_id}: {r.describe()}")
    jo = (r.json().get("result") or {}).get("jobOpening") or {}
    if not jo:
        return None
    loc = jo.get("location") or {}
    return build_posting(
        ats="bamboohr", board=slug, job_id=job_id, company=company, title=jo.get("jobOpeningName", ""),
        url=f"https://{slug}.bamboohr.com/careers/{job_id}", description_html=jo.get("description"),
        locations=[", ".join(x for x in (loc.get("city"), loc.get("state")) if x)],
        remote_flag=bool(jo.get("isRemote")), posted=jo.get("datePosted"), source=source,
        extra_pay_text=str(jo.get("compensation") or ""),
        evidence=f"BambooHR detail endpoint returned job {job_id} on this run",
    )
