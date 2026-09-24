# Job radar build plan

Status legend: [x] done, [~] in progress, [ ] todo, [-] skipped (reason noted)

## Decisions (from kickoff, 2026-09-24)
- User-Agent contact: sethnrosenberg@gmail.com
- API keys: none for now (USAJobs, Adzuna, SerpAPI channels are skipped and logged)
- Schedule: none (run `python -m radar refresh` or `/refresh-jobs` by hand)
- `make` is not installed on this machine; `python -m radar ...` is the primary entry point, Makefile provided for WSL/CI.

## Phase 0: Setup
- [x] Package layout, requirements, .env.example, .gitignore
- [x] Polite HTTP client: 1 req/s/host (cross-process), retries + backoff, robots.txt (RFC 9309 wildcards, crawl-delay), cache/, UA with email, per-request log
- [x] SQLite schema (data/jobs.sqlite): postings, snapshots, board_jobs, leads, judgments, runs
- [x] Run log writer (out/run_log.md)

## Phase 1: Re-verify seed list  -> CHECKPOINT: show user before moving on
- [x] Parse seeds/current_list.md (25 open rows + 8 closed)
- [x] Verifiers: Greenhouse, Ashby, Lever, Workday, SuccessFactors RMK (Burford/Fitch), JSON-LD generic (Point72, D. E. Shaw, Harvey, Citadel), NY AG PDF, Jane Street feed
- [x] Re-check the 8 closed entries on their employer boards
- [x] Write out/seed_verification_2026-09-24.md (awaiting user review)

## Phase 2: Full ATS board pulls for the registry
- [ ] ATS detection (careers-page link scan, then API probes in spec order); write back seeds/companies.csv
- [ ] Pull every job; bucket NYC / US-remote / other US

## Phase 3: Discovery channels (parallel subagents -> data/leads.jsonl)
- [ ] ATS-wide discovery (Common Crawl pending robots decision; web search site: queries)
- [ ] Official APIs (The Muse; USAJobs/Adzuna/SerpAPI skipped, no keys)
- [ ] Public-sector portals (NYDFS, NY AG, NY state, NY Fed, FINRA)
- [ ] Hacker News "Who is hiring"
- [ ] Wayback recurrence check (Octus, 9fin, Debtwire, Burford, Point72, Harvey)
- [ ] Aggregator leads via WebSearch (BuiltIn, legal.io, GoInhouse, JobLeads) -> verify on employer ATS

## Phase 4: Parse, verify, score
- [ ] Verify every candidate on the posting itself; extract fields
- [ ] Pay: structured fields first, then regex
- [ ] Rule-based rubric + subagent judgment batches (sales-attached, domain-years floor, litigation accepted)
- [ ] Dedupe by company + normalized title + location

## Phase 5: Output
- [ ] out/open_positions_YYYY-MM-DD.md, out/jobs.csv, out/diff_YYYY-MM-DD.md, out/run_log.md, seeds/companies.csv

## Phase 6: Repeatable
- [ ] `python -m radar refresh` (+ Makefile `refresh`)
- [ ] .claude/commands/refresh-jobs.md
- [-] Weekly schedule (user declined)
- [ ] Optional ntfy/SMTP digest (off unless configured in .env)
