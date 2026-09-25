"""Phase 5: out/open_positions_<date>.md, out/jobs.csv, out/diff_<date>.md, data/snapshots/<date>.csv."""
from __future__ import annotations

import csv
import datetime as dt
import json

from . import config
from .models import Posting
from .phase1 import ap_date
from .seeds import parse_current_list
from .textutil import norm_company, norm_title

SNAP_DIR = config.DATA / "snapshots"
CSV_FIELDS = ["bucket", "is_new", "fit_score", "company", "title", "url", "location", "loc_bucket", "workplace",
              "pay_display", "pay_min", "pay_max", "pay_type", "pay_period", "pay_source", "years_required", "years_text",
              "jd_required", "sales_attached", "litigation_accepted", "domain_floor", "hard_exclude_reason", "poor_reason",
              "fit_signals", "judgment_rationale", "posted_date", "closes_date", "status", "status_evidence", "verified_at",
              "via_aggregator", "pipeline", "sources", "ats", "board", "job_id", "key"]


def _match_key(company: str, title: str) -> str:
    return f"{norm_company(company)[:8]}|{norm_title(title)}"


def previous_rows(run: str) -> tuple[str, list[dict]]:
    """Last run's snapshot, or the hand-built seed list on the first run."""
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    prior = sorted(p for p in SNAP_DIR.glob("*.csv") if p.stem < run)
    if prior:
        with open(prior[-1], newline="", encoding="utf-8") as f:
            return prior[-1].stem, list(csv.DictReader(f))
    rows, _ = parse_current_list()
    return "seed list", [{"company": r.company, "title": r.title, "url": r.url, "pay_display": r.pay, "bucket": r.section,
                          "status": "open", "years_required": "", "jd_required": ""} for r in rows]


def _esc(s) -> str:
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def _loc(p: Posting) -> str:
    locs = p.locations or [p.location]
    s = "; ".join(locs[:3]) + (f" (+{len(locs) - 3} more)" if len(locs) > 3 else "")
    if p.workplace and p.workplace not in s.lower():
        s += f", {p.workplace}"
    return s or "Not stated"


def _position(p: Posting, new: bool) -> str:
    cell = f"[{_esc(p.title)}]({p.url})"
    if p.closes_date and p.closes_date >= dt.date.today().isoformat():
        cell += f" (apply by {ap_date(p.closes_date)})"
    if new:
        cell += " †"
    if p.via_aggregator:
        cell += f" (aggregator link: {p.via_aggregator})"
    return cell


def _company(p: Posting) -> str:
    return _esc(p.company) + (" (already in your pipeline)" if p.pipeline else "")


def write(posts: list[Posting], closed_notes: list[str], stats: dict) -> dict:
    run = config.run_id()
    base_label, prev = previous_rows(run)
    prev_by_url = {r["url"]: r for r in prev}
    prev_by_key = {_match_key(r["company"], r["title"]): r for r in prev}

    def prior(p: Posting) -> dict | None:
        return prev_by_url.get(p.url) or prev_by_key.get(_match_key(p.company, p.title))

    new = {p.key: (prior(p) is None and not p.pipeline) for p in posts}
    order = lambda p: (-p.fit_score, -(p.pay_max or p.pay_min or 0), p.company)
    fit = sorted([p for p in posts if p.bucket == "fit"], key=order)
    poor = sorted([p for p in posts if p.bucket == "poor"], key=order)
    outside = sorted([p for p in posts if p.bucket == "outside" and not p.poor_reason], key=order)
    today = dt.date.today()

    L = ["# Open positions", "",
         f"Checked on {ap_date(today)}. Links go straight to each posting. Rows marked † are new since the last run "
         f"({base_label if base_label == 'seed list' else ap_date(base_label)}).", "",
         "## Postings that fit your profile", "", "| Position | Company | Location | Listed pay |", "|---|---|---|---|"]
    L += [f"| {_position(p, new[p.key])} | {_company(p)} | {_esc(_loc(p))} | {_esc(p.pay_display)} |" for p in fit]
    L += ["", "## Also open, but a poor match", "", "| Position | Company | Location | Listed pay | Why it's a poor match |", "|---|---|---|---|---|"]
    L += [f"| {_position(p, new[p.key])} | {_company(p)} | {_esc(_loc(p))} | {_esc(p.pay_display)} | {_esc(p.poor_reason)} |" for p in poor]
    L += ["", "## Outside NYC / US-remote", "", "Roles elsewhere in the US that would otherwise fit. Weaker out-of-area matches are in jobs.csv.", "",
          "| Position | Company | Location | Listed pay | Fit |", "|---|---|---|---|---|"]
    L += [f"| {_position(p, new[p.key])} | {_company(p)} | {_esc(_loc(p))} | {_esc(p.pay_display)} | "
          f"{'Fit (' + str(p.fit_score) + ' signals)' if not p.poor_reason else 'Poor match: ' + _esc(p.poor_reason)} |" for p in outside]
    L += ["", "## Checked, not open", ""]
    L += [f"- {n}" for n in closed_notes] or ["None."]
    md = config.OUT / f"open_positions_{today.isoformat()}.md"
    md.write_text("\n".join(L) + "\n", encoding="utf-8")

    rows = []
    for p in sorted(posts, key=lambda p: ({"fit": 0, "poor": 1, "outside": 2}.get(p.bucket, 3),) + order(p)):
        d = p.model_dump()
        d.update(is_new=int(new[p.key]), fit_signals="; ".join(p.fit_signals), sources="; ".join(p.sources))
        rows.append({k: d.get(k, "") for k in CSV_FIELDS})
    for path in (config.OUT / "jobs.csv", SNAP_DIR / f"{run}.csv"):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(rows)

    # ------------------------------------------------------------------- diff
    cur_keys = {_match_key(p.company, p.title) for p in posts} | {p.url for p in posts}
    gone = [r for r in prev if r["url"] not in cur_keys and _match_key(r["company"], r["title"]) not in cur_keys]
    changes = []
    for p in posts:
        r = prior(p)
        if not r:
            continue
        bits = []
        if r.get("pay_display") and r["pay_display"] != p.pay_display and not (r["pay_display"].startswith("$") is False and p.pay_display == "Not listed"):
            bits.append(f"pay {r['pay_display']} → {p.pay_display}")
        if r.get("years_required") not in (None, "") and str(r["years_required"]) != str(p.years_required or ""):
            bits.append(f"years required {r['years_required']} → {p.years_required}")
        if r.get("jd_required") and r["jd_required"] != p.jd_required:
            bits.append(f"JD {r['jd_required']} → {p.jd_required}")
        if r.get("bucket") and r["bucket"] != p.bucket:
            bits.append(f"moved {r['bucket']} → {p.bucket}")
        if bits:
            changes.append(f"- [{_esc(p.title)}]({p.url}), {_esc(p.company)}: " + "; ".join(bits))
    D = [f"# Changes since the last run ({base_label})", "", f"Run {run}.", "",
         f"## New ({sum(new.values())})", ""]
    for b in ("fit", "poor", "outside"):
        ns = [p for p in posts if new[p.key] and p.bucket == b]
        if ns:
            D += [f"**{b}** ({len(ns)})", ""] + [f"- [{_esc(p.title)}]({p.url}), {_esc(p.company)}, {_esc(_loc(p))}, {p.pay_display}"
                                                 + (f", fit {p.fit_score}" if b != "poor" else f": {_esc(p.poor_reason)}") for p in sorted(ns, key=order)] + [""]
    D += [f"## Closed or no longer verifiable ({len(gone)})", ""] + [f"- {_esc(r['title'])}, {_esc(r['company'])} ({r['url']})" for r in gone]
    D += ["", f"## Pay or requirement changes ({len(changes)})", ""] + (changes or ["None."])
    diff = config.OUT / f"diff_{today.isoformat()}.md"
    diff.write_text("\n".join(D) + "\n", encoding="utf-8")

    new_fit = [p for p in fit if new[p.key]]
    return {"open_positions": str(md), "diff": str(diff), "fit": len(fit), "poor": len(poor), "outside": len(outside),
            "new_fit": len(new_fit), "new_poor": sum(new[p.key] for p in poor), "new_outside": sum(new[p.key] for p in outside),
            "closed": len(gone), "top_new_fits": [f"{p.title} | {p.company} | {p.pay_display} | fit {p.fit_score} | {p.url}" for p in new_fit[:5]],
            "baseline": base_label}


def dump_stats(stats: dict) -> None:
    (config.run_dir() / "phase4_stats.json").write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
