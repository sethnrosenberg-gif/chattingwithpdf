# Job radar

Finds, verifies and scores open job postings for one candidate (profile, rubric and rules in
[CLAUDE.md](CLAUDE.md)), then writes them in the format of [seeds/current_list.md](seeds/current_list.md).
Re-run it weekly; git history of `out/` is the posting history.

## Quick start

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env        # optional API keys; every channel works without them or is skipped and logged
python -m radar verify-seeds   # Phase 1 only
```

`make` isn't required; every Makefile target is a thin wrapper over `python -m radar ...`.

## Politeness rules baked into the client (`radar/http.py`)

- 1 request per second per host (or the host's `Crawl-delay`), enforced across processes.
- robots.txt checked on every request and every redirect hop (RFC 9309 wildcards).
- Bot walls, CAPTCHAs and edge-rule 403s are logged as blocked and never worked around.
- User-Agent carries the contact email from `RADAR_CONTACT_EMAIL`.
- Every request, cache hit, block and failure lands in `out/run_log.md`.

## Layout

| Path | What |
|---|---|
| `radar/` | the package (`python -m radar`) |
| `radar/ats/` | Greenhouse, Ashby, Lever, Workday, Workable, Recruitee, BambooHR, SuccessFactors, JSON-LD pages, NY AG |
| `seeds/current_list.md` | the hand-built list the radar started from |
| `seeds/companies.csv` | employer registry with detected ATS and slugs |
| `seeds/watchlist.csv` | closed roles to re-check and aggregator rows to resolve to employer pages |
| `out/` | dated outputs, `jobs.csv`, diffs and the run log |
| `data/` | leads, judgments and per-run snapshots (the SQLite file is local only) |
