"""Phase 1: re-verify every row of seeds/current_list.md (open and closed)."""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass

from . import config, db
from .ats import ashby, greenhouse, lever
from .http import channel
from .models import Posting
from .runlog import record_channel
from .seeds import SeedRow, load_watchlist, parse_current_list
from .textutil import norm_title
from .verify import find_repost, is_aggregator, search_board, verify_url


@dataclass
class SeedResult:
    row: SeedRow
    status: str  # open | closed | unverified
    evidence: str
    posting: Posting | None = None
    url_now: str = ""
    change: str = ""
    method: str = ""


@dataclass
class ClosedResult:
    label: str
    status: str  # reopened | still closed | unverified
    evidence: str
    postings: list[Posting]


def ap_date(d: dt.date | str) -> str:
    if isinstance(d, str):
        d = dt.date.fromisoformat(d)
    months = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]
    return f"{months[d.month - 1]} {d.day}, {d.year}"


def _pay_nums(s: str) -> list[float]:
    out = []
    for m in re.finditer(r"\$\s?([\d,.]+)\s*([KkMm])?", s or ""):
        v = float(m.group(1).replace(",", "").rstrip("."))
        if m.group(2) and m.group(2).lower() == "k":
            v *= 1000
        out.append(v)
    return out


def _compare(row: SeedRow, p: Posting) -> str:
    notes = []
    seed_nums = _pay_nums(row.pay)
    if p.pay_min is not None:
        now = [p.pay_min, p.pay_max]
        if seed_nums and (abs(seed_nums[0] - now[0]) > 1 or (len(seed_nums) > 1 and abs(seed_nums[1] - (now[1] or 0)) > 1)):
            notes.append(f"pay changed: seed said {row.pay}; posting now shows {p.pay_display}")
        elif not seed_nums:
            notes.append(f"pay now listed: {p.pay_display}")
    elif seed_nums:
        notes.append(f"posting shows no pay figure (seed had {row.pay})")
    if p.loc_bucket not in ("nyc", "us_remote"):
        notes.append(f"location is {p.location or 'unspecified'} ({p.loc_bucket.replace('_', ' ')}): belongs in the outside-NYC section")
    notes.extend(_stale_close(p))
    return "; ".join(notes)


def _stale_close(p: Posting) -> list[str]:
    if p.closes_date and p.closes_date < dt.date.today().isoformat():
        return [f"its stated close date ({ap_date(p.closes_date)}) has passed, but the employer system still lists it as open"]
    return []


def _board_of(url: str) -> tuple[str, str] | None:
    if g := greenhouse.parse_url(url):
        return ("greenhouse", g[0]) if g[0] else None
    if a := ashby.parse_url(url):
        return ("ashby", a[0])
    if l := lever.parse_url(url):
        return ("lever", l[0])
    return None


def verify_seeds() -> tuple[list[SeedResult], list[ClosedResult]]:
    rows, closed = parse_current_list()
    watch = load_watchlist()
    results: list[SeedResult] = []
    with channel("phase1:seed-open"):
        for row in rows:
            resolve = next((w for w in watch if w.kind == "resolve" and w.company.lower() in row.company.lower()), None)
            res: SeedResult
            if is_aggregator(row.url):
                # seed rows sourced from aggregators: look for the employer's own posting first
                found = []
                if resolve and resolve.method != "none":
                    st, found = search_board(resolve.method, resolve.target, row.company, resolve.title_regex, source="seed")
                    found = [f for f in found if same_role(row.title, f.title)]
                if found:
                    p = found[0]
                    host = row.url.split("/")[2]
                    if p.ats == "page":
                        # the employer page only lists the title; read the role details from the listing it points to
                        o2 = verify_url(row.url, row.company, source="seed")
                        if o2.posting:
                            p = o2.posting.model_copy(update={
                                "url": p.url, "via_aggregator": None, "location": o2.posting.location or p.location,
                                "status_evidence": p.status_evidence + f"; role details read from the {host} listing ({o2.evidence})",
                            })
                    res = SeedResult(row, "open", p.status_evidence + f" (seed linked to {host}; employer posting found)", p, p.url, method=resolve.method)
                else:
                    o = verify_url(row.url, row.company, source="seed")
                    if o.posting:
                        o.posting.via_aggregator = row.url.split("/")[2]
                    why = f"Employer posting not found ({resolve.note if resolve else 'no employer board known'}); "
                    res = SeedResult(row, o.status, why + o.evidence + (" [aggregator page]" if o.status == "open" else ""), o.posting, row.url if o.posting else "", method=o.method)
            else:
                o = verify_url(row.url, row.company, source="seed")
                res = SeedResult(row, o.status, o.evidence, o.posting, (o.posting.url if o.posting else ""), method=o.method)
                if o.status == "closed":
                    # was it reposted under a new id on the same board?
                    rp, near = None, []
                    if resolve and resolve.method != "none":
                        st, found = search_board(resolve.method, resolve.target, row.company, resolve.title_regex, source="seed")
                        rp = next((f for f in found if same_role(row.title, f.title)), None)
                        near = [f for f in found if f is not rp]
                    elif b := _board_of(row.url):
                        rp = find_repost(row.title, row.company, b[0], b[1])
                    if rp:
                        res = SeedResult(row, "open", f"Original id closed; same role reposted: {rp.status_evidence}", rp, rp.url, method="repost")
                    elif near:
                        res.evidence += "; related opening on the employer's current board (different role, not counted): " + "; ".join(
                            f"[{n.title}]({n.url}) ({n.location}, {n.pay_display})" for n in near[:3])
                elif o.status == "unverified" and resolve and resolve.method != "none":
                    st, found = search_board(resolve.method, resolve.target, row.company, resolve.title_regex, source="seed")
                    found = [f for f in found if same_role(row.title, f.title)]
                    if found:
                        p = found[0]
                        res = SeedResult(row, "open", f"{o.evidence}; employer careers page still lists it: {p.status_evidence}", p, p.url, method=resolve.method)
            if res.posting:
                res.posting.company = row.company
                if res.status == "open":
                    res.change = _compare(row, res.posting)
                    if res.url_now and res.url_now != row.url:
                        res.change = (f"link updated to {res.url_now}; " + res.change).strip("; ")
                    db.upsert_posting(res.posting)
            results.append(res)

    closed_results: list[ClosedResult] = []
    with channel("phase1:seed-closed"):
        for c in closed:
            w = next((w for w in watch if w.kind == "closed" and w.label.lower().startswith(c.company.lower()[:10]) and _similar(w.label, c.title)), None)
            if not w or w.method == "none":
                closed_results.append(ClosedResult(f"{c.company}, {c.title}", "unverified", (w.note if w else "no board to check") + "; nothing to fetch", []))
                continue
            st, found = search_board(w.method, w.target, w.company, w.title_regex, w.location_regex, source="seed-closed")
            if st != "ok" and not found:
                closed_results.append(ClosedResult(f"{c.company}, {c.title}", "unverified", f"{w.method} {w.target}: {st}", []))
            elif found:
                for p in found:
                    db.upsert_posting(p)
                ev = "; ".join(p.status_evidence + "".join(f"; {n}" for n in _stale_close(p)) for p in found)
                closed_results.append(ClosedResult(f"{c.company}, {c.title}", "reopened", ev, found))
            else:
                closed_results.append(ClosedResult(f"{c.company}, {c.title}", "still closed", f"No title matching /{w.title_regex}/ on {w.method} board '{w.target}' this run", []))

    record_channel(
        "phase1:seed-verify", queried=len(rows) + len(closed), candidates=len(rows) + len(closed),
        verified_open=sum(r.status == "open" for r in results) + sum(len(c.postings) for c in closed_results),
        notes=f"{sum(r.status == 'closed' for r in results)} seed rows closed, "
              f"{sum(r.status == 'unverified' for r in results)} unverifiable",
    )
    _save(results, closed_results)
    return results, closed_results


SENIORITY = {"vice", "president", "vp", "associate", "senior", "director", "analyst", "manager", "head", "lead",
             "principal", "managing", "junior", "chief", "counsel", "partner", "intern", "fellow", "staff"}


def same_role(seed_title: str, title: str) -> bool:
    """A repost must keep the seniority words and most of the rest ("VP, X" is not "Associate, X")."""
    a, b = set(norm_title(seed_title).split()), set(norm_title(title).split())
    if (a & SENIORITY) != (b & SENIORITY):
        return False
    rest_a, rest_b = a - SENIORITY - {"and", "of", "the", "for"}, b - SENIORITY - {"and", "of", "the", "for"}
    return not rest_a or len(rest_a & rest_b) / len(rest_a) >= 0.6


def _similar(label: str, title: str) -> bool:
    a = set(re.findall(r"[a-z]{4,}", label.lower()))
    b = set(re.findall(r"[a-z]{4,}", title.lower()))
    return bool(a & b) or not b


def _save(results: list[SeedResult], closed: list[ClosedResult]) -> None:
    d = config.run_dir() / "phase1.json"
    d.write_text(json.dumps({
        "open_rows": [
            {"row": asdict(r.row), "status": r.status, "evidence": r.evidence, "url_now": r.url_now,
             "change": r.change, "method": r.method, "key": r.posting.key if r.posting else None}
            for r in results
        ],
        "closed_rows": [
            {"label": c.label, "status": c.status, "evidence": c.evidence, "keys": [p.key for p in c.postings]}
            for c in closed
        ],
    }, indent=2), encoding="utf-8")


def _esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def write_report(results: list[SeedResult], closed: list[ClosedResult]) -> str:
    today = dt.date.today()
    n_open = sum(r.status == "open" for r in results)
    n_closed = sum(r.status == "closed" for r in results)
    n_unv = sum(r.status == "unverified" for r in results)
    reopened = [c for c in closed if c.status == "reopened"]
    lines = [
        f"# Seed list re-verification",
        "",
        f"Checked on {ap_date(today)}. Every status below comes from a fetch made during this run.",
        "",
        f"- **{n_open} of {len(results)}** open rows are still open, **{n_closed}** have closed and **{n_unv}** couldn't be verified.",
        f"- **{len(reopened)} of {len(closed)}** closed entries have reopened.",
        "",
        "## Open rows from your list",
        "",
        "| Position | Company | Was in | Status now | Location now | Listed pay now | Evidence and changes |",
        "|---|---|---|---|---|---|---|",
    ]
    order = {"open": 0, "unverified": 1, "closed": 2}
    for r in sorted(results, key=lambda r: (order[r.status], r.row.section)):
        p = r.posting
        url = r.url_now or r.row.url
        status = {"open": "Open", "closed": "**Closed**", "unverified": "Couldn't verify"}[r.status]
        if p and p.via_aggregator:
            status += f" (aggregator page, {p.via_aggregator})"
        loc = p.location if p else "—"
        pay = p.pay_display if p else "—"
        ev = r.evidence + (f". {r.change}" if r.change else "")
        lines.append(
            f"| [{_esc(r.row.title)}]({url}) | {_esc(r.row.company)} | {'fit' if r.row.section == 'fit' else 'poor match'} "
            f"| {status} | {_esc(loc)} | {_esc(pay)} | {_esc(ev)} |"
        )
    lines += ["", "## Closed entries re-checked", "", "| Entry | Result | Evidence |", "|---|---|---|"]
    for c in closed:
        res = {"reopened": "**Reopened**", "still closed": "Still closed", "unverified": "Couldn't check"}[c.status]
        ev = c.evidence
        if c.postings:
            ev = "; ".join(f"[{_esc(p.title)}]({p.url}) ({_esc(p.location)}, {p.pay_display})" for p in c.postings) + ". " + ev
        lines.append(f"| {_esc(c.label)} | {res} | {_esc(ev)} |")
    path = config.OUT / f"seed_verification_{today.isoformat()}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)
