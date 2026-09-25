"""Recurrence check: how often do the target seats reopen? (Wayback Machine CDX API)

Writes out/recurrence.md. First-capture dates are upper bounds on posting dates and
sparse captures can hide openings; the report says so.
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
from collections import defaultdict
from urllib.parse import unquote

from .. import config
from ..http import client
from ..runlog import record_channel

FAMILIES = [
    ("legal analyst / bankruptcy / LME / covenant", r"legal analyst|bankruptcy|restructuring|\blme\b|liability management|covenant"),
    ("underwriting", r"underwrit"),
    ("academy / analyst program", r"academy|analyst program|rotational"),
    ("research", r"market intelligence|fundamental research|applied legal research|research analyst|legal research"),
    ("legal engineer", r"legal engineer"),
]
TARGETS = [  # employer, CDX url pattern, title source ("url" = title in the URL slug, "page" = fetch capture)
    ("Octus", "job-boards.greenhouse.io/octus/jobs/*", "page"),
    ("Octus", "boards.greenhouse.io/octus/jobs/*", "page"),
    ("Octus (Reorg)", "boards.greenhouse.io/reorg/jobs/*", "page"),
    ("9fin", "jobs.ashbyhq.com/9fin/*", "page"),
    ("Debtwire (ION)", "jobs.lever.co/ion/*", "page"),
    ("Debtwire (ION)", "iongroup.com/jobs/*", "url"),
    ("Burford", "careers.burfordcapital.com/job/*", "url"),
    ("Point72", "careers.point72.com/CSJobDetail*", "url"),
    ("Harvey", "jobs.ashbyhq.com/harvey/*", "page"),
    ("Harvey", "www.harvey.ai/company/careers/*", "page"),
]
MAX_PAGE_FETCHES = 250
NOISE = r"intern|summer|externship|meet and greet|quant|developer|engineer(?!.*legal)|reporter|campus|university|\bhk\b|\bjp\b|hong kong|singapore|london|tokyo|sydney|asia|europe|\buk\b|\bsg\b"
REQUIRE = {"Debtwire (ION)": r"debtwire"}


def _family(title: str) -> str | None:
    return next((f for f, rx in FAMILIES if re.search(rx, title, re.I)), None)


def _title_from_url(u: str) -> str:
    m = re.search(r"jobName=([^&]+)", u)
    if m:
        return unquote(m.group(1)).replace("-", " ")
    seg = unquote(u.rstrip("/").split("/job/")[-1].split("/jobs/")[-1].split("/")[0])
    return re.sub(r"[-_]+", " ", re.sub(r"[-_][0-9a-f]{8}-[0-9a-f-]{27}$|\d{6,}$", "", seg))


def _title_from_page(html: str) -> str:
    for rx in (r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', r"<title>([^<]+)</title>", r'"title"\s*:\s*"([^"]+)"'):
        m = re.search(rx, html, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def run() -> dict:
    since = (dt.date.today() - dt.timedelta(days=3 * 365)).strftime("%Y%m%d")
    openings: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    queried, fetched, failures = 0, 0, []
    for employer, pattern, how in TARGETS:
        r = client().get("https://web.archive.org/cdx/search/cdx", params={
            "url": pattern, "output": "json", "fl": "timestamp,original", "filter": "statuscode:200",
            "collapse": "urlkey", "from": since, "limit": 3000})
        queried += 1
        if not r.ok:
            failures.append(f"{pattern}: {r.describe()}")
            continue
        rows = r.json()[1:] if r.text.strip() else []
        for ts, orig in rows:
            if re.search(r"/application|/apply|\.(css|js|png)|embed", orig):
                continue
            title = _title_from_url(orig) if how == "url" else ""
            if how == "page":
                if fetched >= MAX_PAGE_FETCHES:
                    continue
                pr = client().get(f"https://web.archive.org/web/{ts}id_/{orig}")
                fetched += 1
                title = _title_from_page(pr.text) if pr.ok else ""
            fam = _family(title)
            if re.search(NOISE, title, re.I) or (employer in REQUIRE and not re.search(REQUIRE[employer], title + orig, re.I)):
                fam = None
            if not fam:
                continue
            key = re.sub(r"\W+", " ", title.lower()).strip()
            rec = openings[(employer, fam)].setdefault(key, {"title": title, "first": ts[:8], "last": ts[:8], "url": orig})
            rec["first"], rec["last"] = min(rec["first"], ts[:8]), max(rec["last"], ts[:8])

    lines = ["# Seat recurrence (Wayback Machine)", "",
             f"Built {config.run_id()} from Wayback CDX captures since {since[:4]}-{since[4:6]}. Capture dates are upper bounds on "
             "when a posting went up, and sparse captures can hide openings entirely, so treat counts as minimums.", "",
             "| Employer | Seat family | Openings found | Per year | Median gap | Watch |", "|---|---|---:|---:|---|---|"]
    detail = []
    summary = []
    for (emp, fam), recs in sorted(openings.items(), key=lambda kv: -len(kv[1])):
        firsts = sorted(dt.datetime.strptime(v["first"], "%Y%m%d").date() for v in recs.values())
        gaps = [(b - a).days for a, b in zip(firsts, firsts[1:]) if (b - a).days > 14]
        med = statistics.median(gaps) if gaps else None
        per_year = len(firsts) / 3
        watch = "check weekly" if med and med < 90 else "check every 2 weeks" if med and med < 180 else "check monthly"
        gap_txt = f"{med / 30:.0f} months" if med else "n/a (one opening)"
        lines.append(f"| {emp} | {fam} | {len(firsts)} | {per_year:.1f} | {gap_txt} | {watch} |")
        summary.append({"employer": emp, "family": fam, "openings": len(firsts), "median_gap_days": med})
        detail += ["", f"### {emp}: {fam}", "", "| Title | First captured | Last captured |", "|---|---|---|"]
        for v in sorted(recs.values(), key=lambda v: v["first"]):
            f, l = v["first"], v["last"]
            detail.append(f"| [{v['title']}](https://web.archive.org/web/{f}/{v['url']}) | {f[:4]}-{f[4:6]}-{f[6:]} | {l[:4]}-{l[4:6]}-{l[6:]} |")
    if not openings:
        lines.append("| — | no matching archived postings found | 0 | | | |")
    if failures:
        lines += ["", "Failures: " + "; ".join(failures)]
    (config.OUT / "recurrence.md").write_text("\n".join(lines + detail) + "\n", encoding="utf-8")
    record_channel("discover:wayback", queried=queried + fetched, candidates=0, failures=failures,
                   notes=f"recurrence report: out/recurrence.md ({len(openings)} employer/family series, {fetched} captures read)")
    return {"series": summary, "cdx_queries": queried, "captures_read": fetched, "failures": failures}
