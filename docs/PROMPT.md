# Kickoff prompt for Claude Code

To use this, unzip the kit, `cd` into the folder, run `claude`, and paste everything below the line.

---

You're building a repeatable job radar for me. Read `CLAUDE.md` first. It has my profile, the scoring rubric and the rules. `seeds/current_list.md` is the list I have now: 25 verified open postings plus 8 closed ones. `seeds/companies.csv` is a starting registry of about 70 target employers with ATS hints (confidence "verified" means the slug worked before; "guess" means you have to detect it).

The goal is to expand that list as far as the evidence allows. Every row must be a verified, currently open posting that links directly to the employer's application page, with listed pay and location, and scored against my rubric. Build it as code that I can re-run weekly and that shows me what changed.

Before you write code, ask me three things in one message: the contact email to put in the User-Agent, which API keys I have or want to register for (USAJobs, Adzuna, SerpAPI, all optional), and whether I want a weekly schedule set up at the end. Then plan the phases below with a todo list and work through them.

## Phase 0: Setup

- Use Python 3.11+ with `httpx`, `selectolax` or `beautifulsoup4`, `pydantic`, `tenacity` and `python-dotenv`, plus `playwright` with Chromium for JavaScript-only pages. If the Playwright MCP server is available, you can use it for exploration. Store data in SQLite (`data/jobs.sqlite`).
- Initialize git so every run's output is diffable. Add a `.env.example`, and `.gitignore` the `.env`.
- Write one polite HTTP client: 1 request per second per host, retries with backoff, a robots.txt check, response caching to `cache/`, and the User-Agent with my email. Log every endpoint hit and failure to `out/run_log.md`.

## Phase 1: Re-verify the seed list

Re-check all 25 open rows in `seeds/current_list.md` for liveness and pay, and re-check the 8 closed ones in case they reopened. This is the first deliverable. Show it to me before moving on.

## Phase 2: Pull full boards from every ATS in the registry

For each company, detect its ATS by probing these public endpoints in order, and write the result back to `companies.csv`:

| ATS | Endpoint |
|---|---|
| Greenhouse | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` (also try `/jobs/{id}?pay_transparency=true` for pay) |
| Lever | `GET https://api.lever.co/v0/postings/{company}?mode=json` |
| Ashby | `GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true` |
| Workday | `POST https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` with body `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}`, paginated. Then `GET .../wday/cxs/{tenant}/{site}{externalPath}` for detail. Guggenheim is `guggenheiminvestment` / `wd5` / `External`. |
| SmartRecruiters | `GET https://api.smartrecruiters.com/v1/companies/{id}/postings` |
| Workable | the public `apply.workable.com/api/v3/accounts/{slug}/jobs` endpoint |
| Recruitee / BambooHR | `{slug}.recruitee.com/api/offers/` and `{slug}.bamboohr.com/careers/list` |
| SuccessFactors-style (Burford, Fitch) | the careers domain's `sitemap.xml` or RSS feed first, then Playwright |
| Avature (Bloomberg) and custom sites (Point72, Jane Street, Citadel, D. E. Shaw, Coinbase) | Playwright. Intercept the XHR/JSON the page itself calls and use that endpoint directly instead of parsing HTML. |

Pull every job, not just keyword hits. Keep rows located in NYC or US-remote, plus a separate bucket for other US locations.

## Phase 3: Discover employers not in the registry

This is where you should find most of the new rows. Run these channels in parallel with subagents, one subagent per channel. Each writes candidates to `data/leads.jsonl` with the source recorded.

1. **ATS-wide discovery.** Query the Common Crawl CDX index (`index.commoncrawl.org`, most recent crawls) for `job-boards.greenhouse.io/*`, `boards.greenhouse.io/*`, `jobs.lever.co/*` and `jobs.ashbyhq.com/*` URLs. Extract board tokens, then filter the tokens by fetching their boards and matching titles. Also run web searches like `site:job-boards.greenhouse.io "clerkship"`, `site:jobs.ashbyhq.com "legal analyst"`, `site:jobs.lever.co "litigation" underwriting`, and so on, built from the keyword families below.
2. **Official APIs.**
   - USAJobs (`data.usajobs.gov/api/search`) for SEC, CFTC, OCC, CFPB, FDIC and Treasury attorney and policy roles in NYC or remote.
   - The Muse public API.
   - Adzuna, if I give you a key.
   - SerpAPI's Google Jobs engine, if I give you a key. Use it only for discovery, then verify on the employer ATS.
3. **Public-sector portals.** NYDFS, NY AG and NY state job listings (these are often PDFs; parse them), the New York Fed careers site, and FINRA careers.
4. **Community feeds.** The monthly Hacker News "Who is hiring" threads (Algolia API: `hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring`), filtered for legal, regulatory, credit, fintech and AI roles in NYC or remote.
5. **Recurrence check.** Use the Wayback Machine CDX API (`web.archive.org/cdx/search/cdx`) on the careers pages of Octus, 9fin, Debtwire, Burford, Point72 and Harvey to see how often legal-analyst, underwriting, academy and research seats reopen. Report the typical cadence so I know which boards to watch.

Use aggregator sites (BuiltIn, legal.io, GoInhouse, JobLeads) only as leads. Search them with WebSearch, then verify each lead on the employer's own posting. Don't scrape LinkedIn, Indeed or Glassdoor.

### Keyword families (match on title and description)

- Include:
  - Titles: "legal analyst", "bankruptcy", "restructuring", "LME", "covenant", "underwriting" or "underwriter" with "litigation" or "legal assets", "applied legal research", "legal engineer" (then check for OTE), "regulatory risk", "regulatory relations", "regulatory strategy", "policy analyst" or "policy counsel" with finance, "product counsel", "payments counsel", "regulatory counsel", "AI governance counsel", "market intelligence", "fundamental researcher", "research associate", "investment analyst program", "rotational associate", "experienced professionals".
  - Description phrases: "clerkship", "J.D.", "law degree", "no finance experience", "financial services background", "prediction markets", "digital assets", "stablecoin", "event-driven", "special situations", "distressed", "litigation finance".
- Exclude or flag: "OTE", "quota", "account executive", "pre-sales", "demo", "Agile", "Scrum", "Python required", "earnings models", "waterfall model", "6+ years leveraged finance", "paralegal", "document review", "10+ years".

## Phase 4: Parse, verify and score

- For every candidate, fetch the posting page itself to confirm it's open. Extract title, company, location and remote status, pay (min, max, type), years required, JD requirement, posted date and the apply URL.
- Pull pay from structured fields first (Ashby compensation, Greenhouse pay ranges, schema.org `JobPosting` JSON-LD `baseSalary`), then regex the description.
- Apply the `CLAUDE.md` rubric. Use subagents in parallel batches for the judgment calls: sales-attached or not, domain-years floor, whether litigation is accepted. Each subagent returns structured JSON with a one-line rationale quoting the posting.
- Deduplicate across sources by company plus normalized title plus location. Prefer the employer ATS link.

## Phase 5: Output

Write these files:

- `out/open_positions_YYYY-MM-DD.md`, in exactly the format of `seeds/current_list.md`:
  - "Postings that fit your profile," sorted by `fit_score`, then pay.
  - "Also open, but a poor match," with the reason.
  - "Outside NYC / US-remote."
  - "Checked, not open."
  - Mark rows new since the last run with †. Each position name links to the posting.
- `out/jobs.csv`, with every field.
- `out/diff_YYYY-MM-DD.md`: new, closed, and pay or requirement changes since the last run.
- `out/run_log.md`: per-channel counts (queried, candidates, verified open, kept), failures, and blocked or skipped sites with the reason.
- An updated `seeds/companies.csv` with the detected ATS types and slugs.

## Phase 6: Make it repeatable

- Add a `make refresh` target (or `python -m radar refresh`) that runs phases 1 through 5.
- Add a `/refresh-jobs` project slash command in `.claude/commands/` that runs it and summarizes the diff.
- If I said yes to scheduling, add either a cron entry or a GitHub Actions workflow on a weekly schedule. It should commit the new `out/` files so git history becomes the posting history.
- Optionally, send a short digest of new fit rows to me by email (SMTP from `.env`) or through ntfy.sh.

## Definition of done

- Every row was verified open during this run, links to the employer posting, and shows listed pay or "Not listed."
- No row breaks the hard excludes without landing in the poor-match table.
- The run log accounts for every channel. The finished list has at least as many verified fit rows as the seed. If it doesn't, explain why in the log instead of padding.
- Finish by telling me the counts: new fit rows, new poor-match rows, closed rows and the top 5 new fits.
