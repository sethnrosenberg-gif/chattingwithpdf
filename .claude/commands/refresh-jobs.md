---
description: Re-run the job radar (phases 1-5), judge new rows, and summarize what changed
---

Refresh the job radar and report what changed. Follow CLAUDE.md (rubric and site rules) throughout.

1. Web-search discovery (the one channel code can't run by itself). Replay the queries in
   `seeds/search_queries.csv` with WebSearch. For every result that shows a specific posting
   (title and company visible; skip LinkedIn, Indeed and Glassdoor), write one JSON line
   `{"source": "websearch:<domain>", "url": ..., "company": ..., "title": ..., "location": ..., "note": "<query>"}`
   to `data/websearch_leads_<today>.jsonl`, then run
   `python -m radar import-leads data/websearch_leads_<today>.jsonl`. Don't open result pages;
   the radar verifies every lead itself.

2. Run the pipeline (discovery channels run in parallel, then board pulls, verification, scoring, output):
   `PYTHONIOENCODING=utf-8 python -m radar refresh`

3. If the summary lists `judgment_batches_pending`, judge them in parallel: one subagent per batch file in
   `data/judgments/pending/`. Each subagent reads its batch and CLAUDE.md, and writes
   `data/judgments/results/<same name>.json`: a list of objects with
   `key, desc_hash, sales_attached (Y/N), domain_floor_years (int or null), domain (str), meets_floor (Y/N/stretch),
   litigation_accepted (Y/N/unclear), jd (Y/N/pref), hard_exclude ("" or reason), rationale` (one line quoting the posting).
   Then run `python -m radar apply-judgments` and `PYTHONIOENCODING=utf-8 python -m radar score`.

4. Summarize for the user from `out/diff_<today>.md` and the final summary JSON: counts of new fit rows,
   new poor-match rows and closed rows, the top 5 new fits (title, company, pay, link), notable pay changes,
   and anything the run log lists as blocked or failed.

5. Commit `out/`, `data/snapshots/`, `data/leads.jsonl`, `data/judgments.jsonl` and `seeds/` with a message like
   `Job radar refresh <date>`.
