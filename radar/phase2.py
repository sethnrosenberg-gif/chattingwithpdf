"""Phase 2: detect each registry employer's ATS, pull every job on its board, keep relevant US rows.

Writes back seeds/companies.csv (ats, slug, status, counts) and stores every pulled job in the
board_jobs table. Relevant NYC / US-remote / other-US postings become Phase 4 candidates
(data/runs/<run>/candidates_boards.jsonl).
"""
from __future__ import annotations

import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote

from . import config, db
from .ats import ashby, greenhouse, html as htmlats, lever, smallats, workday
from .http import channel, client, current_channel
from .keywords import relevance
from .models import Posting
from .runlog import record_channel
from .textutil import norm_company
from .verify import point72_title, point72_urls, verify_url

FIELDS = ["company", "segment", "careers_url", "ats_hint", "ats_slug_or_tenant", "confidence", "notes",
          "ats", "slug", "board_status", "jobs_total", "jobs_relevant_us", "last_checked", "detect_note"]
KEEP = ("nyc", "us_remote", "us_other")

# employers whose postings come through another channel or can't be read
SPECIAL = {
    "jane street": ("janestreet", "janestreet", "Jane Street's own jobs feed (janestreet.com/jobs/main.json)"),
    "point72": ("point72", "careers.point72.com", "careers.point72.com CSSitemap + JSON-LD job pages"),
    "burford capital": ("successfactors", "careers.burfordcapital.com", "SuccessFactors sitemap"),
    "fitch group": ("successfactors", "careers.fitch.group", "SuccessFactors sitemap"),
    "citadel": ("blocked", "", "citadel.com job pages sit behind a Cloudflare challenge; not bypassed"),
    "citadel securities": ("blocked", "", "citadelsecurities.com serves a Cloudflare challenge even on robots.txt; not bypassed"),
    "d. e. shaw": ("blocked", "", "robots.txt disallows /careers/open-roles and the sitemap lists no job pages; individual role URLs are verified when a lead points at them"),
    "bloomberg": ("blocked", "", "bloomberg.avature.net sitemap lists no job pages and job search needs JS; no public JSON feed found"),
    "nydfs": ("channel", "public_sector", "covered by the public_sector discovery channel"),
    "ny attorney general": ("channel", "public_sector", "covered by public_sector (ag.ny.gov refuses this client; statejobs.ny.gov mirrors the postings)"),
    "federal reserve bank of new york": ("channel", "public_sector", "covered by the public_sector discovery channel"),
    "finra": ("channel", "public_sector", "covered by the public_sector discovery channel"),
    "sec": ("channel", "official_apis", "USAJobs (needs an API key)"),
    "cftc": ("channel", "official_apis", "USAJobs (needs an API key)"),
    "occ": ("channel", "official_apis", "USAJobs (needs an API key)"),
    "cfpb": ("channel", "official_apis", "USAJobs (needs an API key)"),
}

ATS_LINK = [
    ("greenhouse", re.compile(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=([\w-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([\w.-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)", re.I)),
    ("workday", re.compile(r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([\w-]+)", re.I)),
    ("recruitee", re.compile(r"([\w-]+)\.recruitee\.com", re.I)),
    ("bamboohr", re.compile(r"([\w-]+)\.bamboohr\.com", re.I)),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([\w-]+)", re.I)),
]
PROBES = [("greenhouse", greenhouse.probe), ("lever", lever.probe), ("ashby", ashby.probe),
          ("workable", smallats.wk_probe), ("recruitee", smallats.rc_probe), ("bamboohr", smallats.bb_probe)]


# ------------------------------------------------------------------ registry file
def load_registry() -> list[dict]:
    with open(config.COMPANIES_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        name = r["company"]
        # "A / B / C" rows are several employers; split them so each gets detected
        outside = re.sub(r"\(.*?\)", "", name)
        if " / " in outside and not r.get("ats"):
            for part in [p.strip() for p in outside.split("/")]:
                out.append({**r, "company": part, "careers_url": "", "ats_slug_or_tenant": "", "confidence": "guess",
                            "notes": f"split from '{name}'" + (f"; {r['notes']}" if r.get("notes") else "")})
        else:
            out.append(r)
    for r in out:
        for k in FIELDS:
            r.setdefault(k, "")
    return out


def save_registry(rows: list[dict]) -> None:
    with open(config.COMPANIES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------- detection
def _slug_guesses(name: str, url: str) -> list[str]:
    base = re.sub(r"\(.*?\)", "", name).replace("&", "and")
    words = re.findall(r"[a-z0-9]+", base.lower())
    stop = {"the", "inc", "llc", "group", "capital", "management", "partners", "advisors", "ai", "and", "co"}
    core = [w for w in words if w not in stop] or words
    g = ["".join(words), "".join(core), "-".join(words)]
    host = re.sub(r"^www\.|^careers\.|^jobs\.", "", re.sub(r"https?://", "", url or "").split("/")[0])
    if host:
        g.append(host.split(".")[0])
    if len(core[0]) >= 5:
        g.append(core[0])
    seen, out = set(), []
    for s in g:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out[:4]


def _name_matches(company: str, board_label: str) -> bool:
    a, b = norm_company(company), norm_company(board_label or "")
    return bool(a and b) and (a in b or b in a or a[:6] == b[:6])


def _scan_careers(url: str) -> tuple[str, str] | None:
    if not url:
        return None
    r = client().get(url)
    if not r.ok:
        return None
    html = r.text
    for ats, rx in ATS_LINK:
        m = rx.search(html)
        if m:
            slug = "|".join(m.groups()) if ats == "workday" else m.group(1)
            if slug.lower() not in ("embed", "js", "www"):
                return ats, slug
    return None


def detect(row: dict) -> tuple[str, str, str]:
    key = row["company"].lower()
    for name, (ats, slug, note) in SPECIAL.items():
        if key == name or key.startswith(name + " "):
            return ats, slug, note
    hint, hslug = (row.get("ats_hint") or "").lower(), row.get("ats_slug_or_tenant") or ""
    if hslug and hint.startswith("workday") and "|" in hslug and ";" not in hslug and row.get("confidence", "").startswith("verified"):
        return "workday", hslug, "registry hint (verified)"
    if hslug and row.get("confidence") == "verified":
        for ats, probe in PROBES:
            if hint.startswith(ats):
                ok, n = probe(hslug)
                if ok:
                    return ats, hslug, f"registry slug confirmed ({n} jobs)"
    for cand in [c for c in hslug.split(";") if c]:
        if "|" in cand:
            spec = workday.spec_from_slug(cand)
            st, jobs = workday.list_jobs(spec, max_pages=1) if spec else ("bad spec", [])
            if st == "ok" and jobs:
                return "workday", cand, "registry Workday hint confirmed"
        else:
            for ats, probe in PROBES:
                if hint.startswith(ats) and probe(cand)[0]:
                    return ats, cand, "registry hint confirmed by probe"
    found = _scan_careers(row.get("careers_url", ""))
    if found:
        return found[0], found[1], f"linked from {row['careers_url']}"
    for slug in _slug_guesses(row["company"], row.get("careers_url", "")):
        for ats, probe in PROBES:
            ok, n = probe(slug)
            if not ok or n == 0:
                continue
            label = greenhouse.board_name(slug) if ats == "greenhouse" else slug
            norm = re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", row["company"]).lower())
            full = slug in (norm, "-".join(re.findall(r"[a-z0-9]+", row["company"].lower())))
            if ats == "greenhouse" and not _name_matches(row["company"], label):
                continue
            if ats != "greenhouse" and not full:
                continue
            return ats, slug, f"probe hit ({n} jobs; board '{label}')"
    return "none", "", "no careers link to a known ATS and no probe hit (greenhouse, lever, ashby, workable, recruitee, bamboohr; smartrecruiters API is robots-blocked)"


# -------------------------------------------------------------------------- pulls
def _relevant(p: Posting, segment: str) -> Posting:
    ok, why = relevance(p.title, p.description, segment)
    p.relevant, p.relevance_reason = ok, why
    return p


def pull(ats: str, slug: str, company: str, segment: str) -> tuple[str, list[Posting]]:
    src = f"board:{ats}"
    if ats in ("greenhouse", "lever", "ashby"):
        st, ps = {"greenhouse": greenhouse.pull, "lever": lever.pull, "ashby": ashby.pull}[ats](slug, company, src)
        return st, [_relevant(p, segment) for p in ps]
    if ats == "recruitee":
        st, ps = smallats.rc_pull(slug, company, src)
        return st, [_relevant(p, segment) for p in ps]
    if ats == "janestreet":
        st, ps = htmlats.janestreet_feed(src)
        return st, [_relevant(p, segment) for p in ps]
    if ats == "workday":
        spec = workday.spec_from_slug(slug)
        st, jobs = workday.list_jobs(spec)
        light = workday.light_postings(spec, company, jobs, src)
        out = []
        for lp, j in zip(light, jobs):
            if relevance(lp.title, "", segment)[0] and lp.loc_bucket in KEEP + ("unknown",):
                try:
                    full = workday.detail(spec, j["externalPath"], company, src)
                except RuntimeError:
                    full = None
                out.append(_relevant(full, segment) if full else lp)
            else:
                out.append(_relevant(lp, segment))
        return st, out
    if ats in ("workable", "bamboohr"):
        st, light = (smallats.wk_pull if ats == "workable" else smallats.bb_pull)(slug, company, src)
        out = []
        for lp in light:
            if relevance(lp.title, "", segment)[0]:
                full = (smallats.wk_detail if ats == "workable" else smallats.bb_detail)(slug, lp.job_id, company, src)
                out.append(_relevant(full, segment) if full else lp)
            else:
                out.append(_relevant(lp, segment))
        return st, out
    if ats == "successfactors":
        st, urls = htmlats.rmk_sitemap(slug)
        out = []
        for u in urls:
            t = htmlats.rmk_title_from_url(u)
            if relevance(t, "", segment)[0] or relevance(t, "litigation", segment)[0]:
                p = htmlats.rmk_verify(u, company, src)
                if p:
                    out.append(_relevant(p, segment))
        return st, out
    if ats == "point72":
        urls = point72_urls()
        out = []
        for u in urls:
            if relevance(point72_title(u), "investment", segment)[0]:
                o = verify_url(u, company, src)
                if o.posting:
                    out.append(_relevant(o.posting, segment))
        return ("ok" if urls else "sitemap unavailable"), out
    if ats == "smartrecruiters":
        return smallats.sr_pull(slug, company, src)[0], []
    return f"no puller for {ats}", []


# ---------------------------------------------------------------------------- run
def _discovered_rows() -> list[dict]:
    path = config.DATA / "discovered_boards.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [{"company": r["company"] or r["board"], "segment": "discovered", "ats": r["ats"], "slug": r["board"],
                 "detect_note": "found by Common Crawl discovery", "discovered": True} for r in csv.DictReader(f)]


def run(companies: list[str] | None = None, redetect: bool = False) -> dict:
    rows = load_registry()
    targets = [r for r in rows if not companies or r["company"] in companies]
    extra = [] if companies else _discovered_rows()
    known = {(r.get("ats"), r.get("slug")) for r in rows}
    extra = [e for e in extra if (e["ats"], e["slug"]) not in known]
    ch = current_channel() if current_channel() != "misc" else "phase2:boards"
    cand_path = config.run_dir() / "candidates_boards.jsonl"
    totals = {"companies": len(targets), "boards_pulled": 0, "jobs": 0, "relevant_us": 0}

    def one(r: dict) -> list[Posting]:
        with channel(ch):
            if redetect or not r.get("ats") or r.get("discovered") is None and r.get("ats") == "none":
                r["ats"], r["slug"], r["detect_note"] = detect(r)
            if r["ats"] in ("none", "blocked", "channel"):
                r["board_status"] = r["ats"]
                r["last_checked"] = config.run_id()
                return []
            try:
                st, ps = pull(r["ats"], r["slug"], r["company"], r.get("segment", ""))
            except Exception as e:  # keep going; the log records it
                st, ps = f"error: {type(e).__name__}: {e}", []
            keep = [p for p in ps if p.relevant and p.loc_bucket in KEEP]
            r.update(board_status=st, jobs_total=len(ps), jobs_relevant_us=len(keep), last_checked=config.run_id())
            db.upsert_board_jobs([{
                "ats": p.ats, "board": p.board, "job_id": p.job_id or p.url, "company": p.company, "title": p.title,
                "location": p.location, "loc_bucket": p.loc_bucket, "url": p.url, "relevant": p.relevant,
                "relevance_reason": p.relevance_reason, "raw": {},
            } for p in ps])
            for p in keep:
                p.segment = r.get("segment")
            return keep

    with ThreadPoolExecutor(10) as ex:
        results = list(ex.map(one, targets + extra))
    cands = [p for ps in results for p in ps]
    with open(cand_path, "a" if companies else "w", encoding="utf-8") as f:
        for p in cands:
            f.write(p.model_dump_json() + "\n")
    save_registry(rows)
    totals["boards_pulled"] = sum(1 for r in targets + extra if str(r.get("board_status", "")).startswith(("ok", "partial")))
    totals["jobs"] = sum(int(r.get("jobs_total") or 0) for r in targets + extra)
    totals["relevant_us"] = len(cands)
    by_status: dict[str, int] = {}
    for r in targets + extra:
        k = str(r.get("board_status") or "?").split(" (")[0][:40]
        by_status[k] = by_status.get(k, 0) + 1
    totals["by_status"] = by_status
    record_channel("phase2:boards", queried=len(targets) + len(extra), candidates=len(cands),
                   skipped=[f"{r['company']}: {r['detect_note']}" for r in targets if r.get("ats") in ("blocked", "none")],
                   notes=f"{totals['boards_pulled']} boards pulled, {totals['jobs']} jobs, {len(extra)} Common Crawl boards; status {json.dumps(by_status)}")
    return totals
