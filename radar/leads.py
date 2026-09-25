"""data/leads.jsonl: candidates from discovery channels, appended safely by parallel processes."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import config
from .filelock import locked
from .models import Lead

_LOCK = config.DATA / ".leads.lock"


def add_leads(leads: list[Lead], path: Path = config.LEADS_PATH) -> int:
    """Append leads, skipping (source, url) pairs already recorded in this run. Returns count written."""
    if not leads:
        return 0
    run = config.run_id()
    with locked(_LOCK):
        seen = {(l["source"], l["url"]) for l in read_leads(path) if l.get("run") == run}
        n = 0
        with open(path, "a", encoding="utf-8") as f:
            for lead in leads:
                if (lead.source, lead.url) in seen:
                    continue
                seen.add((lead.source, lead.url))
                rec = lead.model_dump()
                rec["run"] = run
                rec["found_at"] = rec.get("found_at") or time.strftime("%Y-%m-%dT%H:%M:%S")
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    return n


def read_leads(path: Path = config.LEADS_PATH, run: str | None = None) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if run is None or d.get("run") == run:
                out.append(d)
    return out
