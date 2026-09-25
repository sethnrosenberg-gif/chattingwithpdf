# Job radar

Finds, verifies and scores open job postings for one candidate (profile, rubric and rules in
[CLAUDE.md](CLAUDE.md)), then writes them in the format of [seeds/current_list.md](seeds/current_list.md).
Re-run it weekly; git history of `out/` is the posting history.

## Quick start

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env        # optional API keys; every channel works without them or is skipped and logged
python -m radar refresh        # phases 1-5; or run /refresh-jobs in Claude Code
```

In Claude Code, `/refresh-jobs` does everything: it replays the web searches in
`seeds/search_queries.csv`, runs the pipeline, sends new fit rows to judgment subagents,
re-scores, summarizes the diff and commits the outputs.

| Command | What it does |
|---|---|
| `python -m radar refresh` | Phase 1 seed check, discovery channels in parallel, board pulls, verification, scoring, outputs |
| `python -m radar verify-seeds` | Phase 1 only, writes `out/seed_verification_<date>.md` |
| `python -m radar boards [--company X]` | Phase 2: ATS detection and full board pulls, updates `seeds/companies.csv` |
| `python -m radar discover <channel>` | One Phase 3 channel: `commoncrawl`, `public_sector`, `official_apis`, `hn`, `wayback`, `websearch` |
| `python -m radar import-leads <file>` | Add web-search leads (JSONL) gathered by Claude |
| `python -m radar score` | Phases 4-5 again on today's data (after judgments) |
| `python -m radar apply-judgments` | Merge subagent judgments from `data/judgments/results/` |

## Outputs

| File | What |
|---|---|
| `out/open_positions_<date>.md` | the list, in the format of `seeds/current_list.md` (fit, poor match, outside NYC, not open); † marks rows new since the last run |
| `out/jobs.csv` | every kept posting with every field, including the long tail not shown in the markdown (`bucket=low`) |
| `out/diff_<date>.md` | new, closed, and pay or requirement changes since the last run |
| `out/run_log.md` | per-channel counts, blocked sites, failures, every request |
| `out/recurrence.md` | how often the watched seats reopen (Wayback Machine) |
| `out/seed_verification_<date>.md` | the Phase 1 re-check of the seed list |

`make` isn't required; every Makefile target is a thin wrapper over `python -m radar ...`.

## Running on GitHub and the Lovable app

`.github/workflows/refresh.yml` runs `python -m radar refresh` on GitHub's servers and commits the results. Start it
from the repo's Actions tab ("refresh" → Run workflow) or from a front end through the GitHub API. It has no schedule
unless you add one. Those runs can't make the Claude judgment calls, so run `/refresh-jobs` afterwards to judge new rows.
[docs/LOVABLE.md](docs/LOVABLE.md) has the prompt and build steps for a Lovable dashboard over these outputs.

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
| `data/` | `leads.jsonl`, `judgments.jsonl`, `snapshots/<date>.csv` (drives diffs and †), Common Crawl sweep state (`cc_boards.json`, `discovered_boards.csv`); the SQLite file is local only |

## Scoring notes

The CLAUDE.md rubric is applied in `radar/score.py`. Three extra poor-match rules encode the
"what he wants" section: in-house seats in off-target practice areas (employment, real estate,
commercial contracts, corporate/securities, IP, tax), law-firm associate seats, and contract or
hourly work. A posting needs 3 of the 10 fit signals for the fit table. Judgment calls
(sales-attached, domain-years floor, litigation accepted) come from subagents and are cached in
`data/judgments.jsonl` by posting and description hash, so unchanged postings aren't re-judged.

## Known limits

- Blocked, never worked around: citadel.com and citadelsecurities.com (Cloudflare), jobleads.com (Cloudflare),
  ag.ny.gov (403 to scripted clients; statejobs.ny.gov mirrors its postings), api.smartrecruiters.com (robots.txt),
  deshaw.com/careers/open-roles (robots.txt). D. E. Shaw and Bloomberg have no readable job feed.
- index.commoncrawl.org is robots-exempted by the user's choice (`RADAR_ROBOTS_EXEMPT_HOSTS`); each run checks up to
  1,500 unseen boards per ATS and carries the rest forward.
- USAJobs, Adzuna and SerpAPI run only with keys in `.env`.
