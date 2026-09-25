"""Phase 4: turn seeds, board pulls and discovery leads into verified, deduplicated, scored postings."""
from __future__ import annotations

import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from . import config, db
from .ats import ashby, greenhouse, lever
from .ats.base import build_posting
from .ats.nyag import pdf_text
from .extract import classify_location
from .http import channel, client, current_channel
from .keywords import relevance
from .leads import read_leads
from .models import Posting
from .phase1 import same_role
from .runlog import record_channel
from .score import JUDGMENTS, _role_key, desc_hash, judgments, score
from .textutil import html_to_text, jsonld_jobposting, norm_company
from .verify import is_aggregator, verify_url

KEEP = ("nyc", "us_remote", "us_other")
PENDING = config.DATA / "judgments" / "pending"
RESULTS = config.DATA / "judgments" / "results"


# ---------------------------------------------------------------- lead resolution
def _page_posting(url: str, company: str, title: str, location: str, source: str, listed_on: str) -> Posting | None:
    r = client().get(url)
    if not r.ok:
        return None
    is_pdf = url.lower().split("?")[0].endswith(".pdf") or "pdf" in r.headers.get("content-type", "")
    text = pdf_text(r.content) if is_pdf else html_to_text(r.text)
    if not is_pdf and (jp := jsonld_jobposting(r.text)):
        from .ats.html import jsonld_verify

        return jsonld_verify(url, company, source, html=r.text)
    if not location:
        m = re.search(r"(?:location|duty station|work location)[:\s]+([^\n]{3,60})", text, re.I)
        location = re.split(r"\s{2,}|business unit|salary|negotiating|title:|\bgrade\b", m.group(1), flags=re.I)[0].strip(" ,:") if m else ("New York, NY" if re.search(r"new york,? ny|one state street|manhattan", text, re.I) else "")
    return build_posting(ats="page", board=urlsplit(url).netloc, job_id=None, company=company, title=title, url=url,
                         description_text=text, locations=[location], source=source,
                         evidence=f"Listed on {listed_on} this run; posting document fetched (HTTP {r.status})")


def _registry() -> dict[str, tuple[str, str]]:
    out = {}
    with open(config.COMPANIES_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("ats") in ("greenhouse", "lever", "ashby") and r.get("slug"):
                out[norm_company(r["company"])] = (r["ats"], r["slug"])
    return out


def _employer_board(company: str, reg: dict) -> tuple[str, str] | None:
    key = norm_company(company)
    if key in reg:
        return reg[key]
    for guess in {key, re.sub(r"[^a-z0-9]", "", company.lower().split()[0]) if company else ""}:
        if len(guess) < 3:
            continue
        for ats, probe in (("greenhouse", greenhouse.probe), ("lever", lever.probe), ("ashby", ashby.probe)):
            ok, n = probe(guess)
            if ok and n:
                if ats == "greenhouse" and norm_company(greenhouse.board_name(guess) or "")[:5] != key[:5]:
                    continue
                return ats, guess
    return None


def resolve_lead(lead: dict, reg: dict) -> tuple[str, Posting | None, str]:
    """(status, posting, evidence) for one lead, verified on the employer's own system where possible."""
    url, company, title, src = lead["url"], lead.get("company") or "", lead.get("title") or "", lead["source"]
    if src.startswith("public_sector:") and not re.search(r"greenhouse|lever|ashby|myworkdayjobs", url):
        p = _page_posting(url, company, title, lead.get("location") or "", src, src.split(":", 1)[1])
        return ("open", p, p.status_evidence) if p else ("unverified", None, "posting document did not load")
    if not is_aggregator(url) and not url.startswith("https://news.ycombinator.com"):
        o = verify_url(url, company, src)
        if o.posting and not o.posting.title:
            o.posting.title = title
        return o.status, o.posting, o.evidence
    # aggregator / HN lead: find the employer's own posting
    board = _employer_board(company, reg) if company else None
    if board:
        pull = {"greenhouse": greenhouse.pull, "lever": lever.pull, "ashby": ashby.pull}[board[0]]
        st, ps = pull(board[1], company, src)
        hit = next((p for p in ps if same_role(title, p.title)), None)
        if hit:
            return "open", hit, hit.status_evidence + f" (lead from {urlsplit(url).netloc}; employer posting found)"
        if st == "ok":
            return "unverified", None, f"employer board {board[0]}:{board[1]} has no matching title"
    if is_aggregator(url) and "linkedin" not in url and "indeed" not in url and "glassdoor" not in url:
        o = verify_url(url, company, src)
        if o.posting:
            o.posting.via_aggregator = urlsplit(url).netloc
        return o.status, o.posting, "employer posting not found; " + o.evidence
    return "unverified", None, "no employer posting found for this lead"


# ------------------------------------------------------------------------ gather
def gather(verify_leads: bool = True) -> tuple[list[Posting], dict]:
    run = config.run_id()
    stats: dict = {"seed": 0, "boards": 0, "leads": 0, "leads_verified": 0, "leads_unverified": 0, "by_source": {}}
    posts: list[Posting] = []
    ph1 = config.run_dir() / "phase1.json"
    seed_keys: set[str] = set()
    if ph1.exists():
        d = json.loads(ph1.read_text(encoding="utf-8"))
        keys = [r["key"] for r in d["open_rows"] if r["key"] and r["status"] == "open"] + [k for c in d["closed_rows"] for k in c["keys"]]
        for k in keys:
            if (p := db.get_posting(k)):
                p.sources = sorted(set(p.sources) | {"seed"})
                posts.append(p)
                seed_keys.add(k)
        stats["seed"] = len(seed_keys)
    cb = config.run_dir() / "candidates_boards.jsonl"
    if cb.exists():
        for line in cb.read_text(encoding="utf-8").splitlines():
            posts.append(Posting.model_validate_json(line))
            stats["boards"] += 1

    if verify_leads:
        reg = _registry()
        leads = read_leads(run=run)
        stats["leads"] = len(leads)
        ch = current_channel()

        def one(lead):
            with channel(ch):
                try:
                    return lead, *resolve_lead(lead, reg)
                except Exception as e:
                    return lead, "unverified", None, f"{type(e).__name__}: {e}"

        with ThreadPoolExecutor(8) as ex:
            for lead, st, p, ev in ex.map(one, leads):
                s = stats["by_source"].setdefault(lead["source"].split(":")[0], {"leads": 0, "verified_open": 0, "unverified": 0, "closed": 0})
                s["leads"] += 1
                if st == "open" and p:
                    p.sources = sorted(set(p.sources) | {lead["source"]})
                    posts.append(p)
                    s["verified_open"] += 1
                    stats["leads_verified"] += 1
                elif st == "closed":
                    s["closed"] += 1
                else:
                    s["unverified"] += 1
                    stats["leads_unverified"] += 1
    return posts, stats


def dedupe(posts: list[Posting]) -> list[Posting]:
    rank = lambda p: (0 if "seed" in p.sources else 1, 0 if p.loc_bucket == "nyc" else 1, 0 if p.ats not in ("page", "jsonld", None) else 1,
                      1 if p.via_aggregator else 0, -len(p.description))
    by_key: dict[str, Posting] = {}
    for p in sorted(posts, key=rank):
        k = p.dedupe_key()
        if k in by_key:
            by_key[k].sources = sorted(set(by_key[k].sources) | set(p.sources))
        else:
            by_key[k] = p
    return list(by_key.values())


def display_company(p: Posting) -> str:
    """Discovery gives board slugs ('moonpay', 'ironcladhq'); turn them into readable employer names."""
    c = p.company or ""
    if c and (c != (p.board or "") and not re.fullmatch(r"[a-z0-9._-]+", c)):
        return c
    if p.ats == "greenhouse" and p.board:
        name = greenhouse.board_name(p.board)
        if name:
            return name
    m = re.search(r"@\s*([A-Z][\w&.' -]{1,40})$", p.title)
    if m:
        return m.group(1).strip()
    if c.startswith("jobs-page-"):
        return "Unnamed employer (Ashby board)"
    c = re.sub(r"(hq|inc|jobs|careers)$", "", c.replace("-", " ").replace("_", " ")).strip()
    return c.title() if c.islower() else c


def run(verify_leads: bool = True) -> tuple[list[Posting], dict]:
    posts, stats = gather(verify_leads)
    posts = [p for p in posts if p.status == "open"]
    from .extract import best_bucket

    import html as htmllib

    for p in posts:
        p.url = htmllib.unescape(p.url)
        if p.key.startswith("url:"):  # rows stored before the url_key fix collided on query-string URLs
            from .ats.base import url_key

            p.key = url_key(p.url)
        if p.locations:  # recompute with current rules; stored rows may predate a fix
            p.loc_bucket = best_bucket(p.locations, remote_flag=(p.workplace == "remote") or None)
        p.relevant, p.relevance_reason = relevance(p.title, p.description, p.segment)
        if "seed" in p.sources:
            p.relevant = True
    posts = [p for p in posts if p.relevant and p.loc_bucket in KEEP + ("unknown",)]
    ch = current_channel()
    with channel(ch):
        for p in posts:
            p.company = display_company(p)
    posts = dedupe(posts)

    def pay(p):
        with channel(ch):
            return greenhouse.enrich_pay(p) if p.ats == "greenhouse" and not p.pay_source.startswith("greenhouse") else p

    with ThreadPoolExecutor(4) as ex:
        posts = list(ex.map(pay, posts))
    posts = [score(p) for p in posts if p.status == "open"]
    for p in posts:
        db.upsert_posting(p)
    stats["kept"] = len(posts)
    stats["buckets"] = {b: sum(p.bucket == b for p in posts) for b in ("fit", "poor", "outside")}
    return posts, stats


# -------------------------------------------------------------------- judgments
QUAL = re.compile(r"(qualifications|requirements|what you.ll need|you have|about you|experience|who you are|you will|responsibilit)", re.I)


def export_judgments(posts: list[Posting], batch_size: int = 20) -> list[str]:
    """Write batches for subagents: postings in fit/outside or near-fit poor rows lacking a cached judgment."""
    PENDING.mkdir(parents=True, exist_ok=True)
    for f in PENDING.glob("*.json"):
        f.unlink()
    cached = judgments()
    need = [p for p in posts if (p.bucket == "fit" or (p.bucket == "outside" and not p.poor_reason))
            and not (p.key in cached and cached[p.key].get("desc_hash") == desc_hash(p))
            and _role_key(p.company, p.title) not in cached]
    files = []
    for i in range(0, len(need), batch_size):
        items = []
        for p in need[i:i + batch_size]:
            m = QUAL.search(p.description)
            body = p.description[m.start() - 200 if m and m.start() > 200 else 0:][:3500]
            items.append({"key": p.key, "desc_hash": desc_hash(p), "company": p.company, "title": p.title,
                          "location": p.location, "pay": p.pay_display, "url": p.url, "posting_excerpt": body})
        path = PENDING / f"batch_{i // batch_size + 1:02d}.json"
        path.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
        files.append(str(path))
    return files


def apply_judgments() -> int:
    """Merge subagent results (data/judgments/results/*.json) into data/judgments.jsonl."""
    n = 0
    hashes = {x["key"]: x["desc_hash"] for f in PENDING.glob("*.json") for x in json.loads(f.read_text(encoding="utf-8"))}
    with open(JUDGMENTS, "a", encoding="utf-8") as out:
        for f in sorted(RESULTS.glob("*.json")):
            for d in json.loads(f.read_text(encoding="utf-8")):
                d["judged_on"] = config.run_id()
                d.setdefault("desc_hash", hashes.get(d["key"]))
                out.write(json.dumps(d, ensure_ascii=False) + "\n")
                n += 1
            f.rename(f.with_suffix(".applied"))
    return n
