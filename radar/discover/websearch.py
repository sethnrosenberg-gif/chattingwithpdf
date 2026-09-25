"""Web-search discovery (site: queries on ATS domains and aggregator sites).

Searches need a search engine, which this code doesn't have without a SerpAPI key, so Claude runs
them with its WebSearch tool during /refresh-jobs, replaying seeds/search_queries.csv, and imports
the hits with `python -m radar import-leads <file> --source websearch:...`. This module only
records the channel's counts for the run log.
"""
from __future__ import annotations

import csv

from .. import config
from ..leads import read_leads
from ..runlog import record_channel

QUERIES = config.SEEDS / "search_queries.csv"


def run() -> dict:
    leads = [l for l in read_leads(run=config.run_id()) if l["source"].startswith("websearch")]
    n_queries = 0
    if QUERIES.exists():
        with open(QUERIES, newline="", encoding="utf-8") as f:
            n_queries = sum(1 for _ in csv.DictReader(f))
    skipped = [] if leads else ["no web-search leads imported this run (run /refresh-jobs in Claude Code to replay seeds/search_queries.csv)"]
    record_channel("discover:websearch", queried=n_queries, candidates=len(leads), skipped=skipped,
                   notes="queries run by Claude via WebSearch; leads imported with import-leads")
    return {"queries": n_queries, "leads": len(leads)}
