# Building a front end for the radar in Lovable

Lovable builds React front ends with a Supabase backend. It can't run this Python project, so the split is:

- **The radar does the sweeping** on GitHub's servers (`.github/workflows/refresh.yml`) and commits results to this repo.
- **The Lovable app is the front end**: it reads those files, lets you triage postings, and its "Run sweep now"
  button starts the workflow through the GitHub API.

## Setup before building the sweep button

1. Create a fine-grained GitHub token scoped to this repo with **Actions: read and write** and **Contents: read**.
2. In Lovable, connect Supabase and add the token as the secret `GITHUB_TOKEN`.
3. Point Lovable's own GitHub sync at a **separate** repo, not this one, so app code doesn't mix with the radar.
4. If this repo is private, the app reads data through a Supabase Edge Function using the same token.

## The prompt (paste as the first message)

````markdown
# Build: "Job Radar" — a clean dashboard over an existing job-sweeping engine

## What already exists (do NOT rebuild it)
I have a Python project on GitHub, repo `sr104696/Claudey`. It is a "job radar": each run it checks ~120 target
employers' job boards (Greenhouse, Lever, Ashby, Workday, etc.), discovers new employers, verifies every posting is
still open on the employer's own site, scores each against my candidate rubric (CLAUDE.md), and commits dated results
to the repo. It respects robots.txt and rate limits (1 request/sec/host) and takes 30–90 minutes per run. It keeps
running in Python via GitHub Actions. You cannot run it inside this app.

Your job: build a friendly web app that (1) displays the radar's results, (2) lets me triage postings, and
(3) has a button that triggers a new sweep on GitHub and shows its progress. Hide all the complexity.

## Where the data lives (read-only for the app)
Raw files: `https://raw.githubusercontent.com/sr104696/Claudey/main/<path>`
(If the repo is private, fetch through a Supabase Edge Function using the `GITHUB_TOKEN` secret, never in the browser.)

| File | What it is | How the app uses it |
|---|---|---|
| `out/jobs.csv` | Latest run: every kept posting, one row each | Primary data source |
| `data/snapshots/YYYY-MM-DD.csv` | Same columns, one file per past run | History / what changed |
| `out/diff_YYYY-MM-DD.md` | New / closed / pay changes vs the previous run | "What's new" panel |
| `out/open_positions_YYYY-MM-DD.md` | Human-readable list | "Download report" link |
| `out/recurrence.md` | How often key seats reopen, by employer | Watch list page |
| `out/run_log.md` | Technical log (very long) | Link only, under Advanced |
| `seeds/companies.csv` | Target employers + detected job-board system | Employers page |
| `CLAUDE.md` | My profile and the scoring rubric | "How scoring works" page |

Find the newest dated files via `GET https://api.github.com/repos/sr104696/Claudey/contents/out` and
`.../contents/data/snapshots`, picking the latest date in the filenames.

### `out/jobs.csv` columns (the data contract)
`bucket` (fit | poor | outside | low), `is_new` (1/0), `fit_score` (0–10), `company`, `title`, `url` (employer's
posting = apply link), `location`, `loc_bucket` (nyc | us_remote | us_other), `workplace`, `pay_display` (ready to show),
`pay_min`, `pay_max`, `pay_type` (base | OTE | hourly | not listed), `pay_period`, `pay_source`, `years_required`,
`years_text`, `jd_required` (Y/N/pref), `sales_attached` (Y/N), `litigation_accepted`, `domain_floor`,
`hard_exclude_reason`, `poor_reason`, `fit_signals` ("; "-separated), `judgment_rationale`, `posted_date`,
`closes_date`, `status`, `status_evidence`, `verified_at`, `via_aggregator`, `pipeline` (True = already in my
pipeline), `sources`, `ats`, `board`, `job_id`, `key` (stable unique id — primary key everywhere).

## Pages and UX (simple, clean, mobile-friendly)
1. **Home**: stat cards (Great fits, New this week, Closed since last run, Last sweep date); "What's new" list of new
   fit rows; primary button **Run sweep now**; secondary **Download report**.
2. **Jobs**: tabs Great fits (fit) · Long shots (poor) · Other US cities (outside) · All. Sort fit_score desc, then
   pay_max desc. Search; filters New only, Remote only, Min pay, Hide pipeline companies, JD required. Card: title,
   company, location and pay chips, 0–10 fit meter, New badge, "Apply on employer site" (opens `url`), expandable
   "Why": fit_signals as green chips, poor_reason in amber, judgment_rationale as a quote, closes_date if present.
3. **My pipeline**: mark postings Interested / Applied / Interviewing / Rejected / Not for me with notes; Kanban by
   status; stored in Supabase by `key`; show "No longer listed" when a tracked key leaves the latest jobs.csv.
4. **History**: compare two snapshot dates on `key` (added / removed / pay changed).
5. **Employers**: seeds/companies.csv with plain labels ("Checked ✓", "Blocked by site", "No job board found").
6. **Watch list**: render out/recurrence.md. **How it works**: render CLAUDE.md's rubric. **Advanced**: run log link.

## Sweeps
- Edge Function `trigger-sweep`: `POST https://api.github.com/repos/sr104696/Claudey/actions/workflows/refresh.yml/dispatches`
  with `{"ref":"main","inputs":{"skip_commoncrawl":"false"}}`, auth `Bearer GITHUB_TOKEN`.
- Edge Function `sweep-status`: `GET .../actions/workflows/refresh.yml/runs?per_page=1` → status, conclusion, times.
- UI: after clicking, show "Sweep running — usually 30–90 minutes, you can close this page"; poll every 60 s; when
  complete, reload data and toast "New results ready". Disable the button while a run is in progress. Offer a
  "Quick sweep" option that sets skip_commoncrawl to true.

## Rules (from CLAUDE.md)
- Read-only toward job sites: never apply, submit forms or contact anyone; "Apply" only opens the employer page.
  No scraping from the app; all fetching happens in the Python radar.
- Show pay exactly as listed (`pay_display`), "Not listed" when empty. Mark `via_aggregator` rows.

## Tech
React + Tailwind + shadcn/ui; PapaParse for CSV; react-markdown + remark-gfm. Supabase magic-link auth (just me) and
table `tracked_postings(key text primary key, status text, notes text, updated_at timestamptz, snapshot jsonb)` with
RLS to my user. Friendly empty/error states with Retry. Build incrementally.
````

## Follow-up messages (one per message, test between each)

1. Build only the Jobs page reading `out/jobs.csv`, with tabs, search and cards. No backend yet.
2. Add Home: stat cards and "What's new" from the latest `out/diff_*.md`.
3. Connect Supabase; add magic-link login and the My pipeline Kanban (`tracked_postings`).
4. Add `trigger-sweep` and `sweep-status` edge functions and wire the Run sweep now button.
5. Add History, Employers, Watch list and How it works.
6. Polish: mobile layout, loading skeletons, empty states.

## Limits to expect

| Lovable can | Lovable can't |
|---|---|
| Build the UI, filters, charts, Kanban | Run the Python radar (needs Python and up to ~1 hour) |
| Read this repo's files over HTTPS | Crawl job sites itself (edge functions time out; would break rate limits) |
| Store pipeline notes in Supabase | Make the Claude judgment calls (done by `/refresh-jobs` in Claude Code) |
| Start the GitHub workflow | Show new results before the workflow finishes and commits |

Runs started from the app skip the Claude judgment step: new rows are scored by rule and left in
`data/judgments/pending` (not committed). Run `/refresh-jobs` in Claude Code afterwards to judge them fully.
