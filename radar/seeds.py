"""Parse seeds/current_list.md and seeds/watchlist.csv."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field

from . import config

LINK = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)(?P<rest>.*)")


@dataclass
class SeedRow:
    section: str  # fit | poor
    title: str
    url: str
    company: str
    location: str
    pay: str
    reason: str = ""
    note: str = ""  # trailing text after the link, e.g. "(apply by Oct. 16, 2026)"
    dagger: bool = False


@dataclass
class ClosedSeed:
    company: str
    title: str
    reason: str


@dataclass
class Watch:
    label: str
    company: str
    method: str  # greenhouse|ashby|lever|workday|point72|rmk|janestreet|page|none
    target: str
    title_regex: str
    location_regex: str = ""
    note: str = ""
    kind: str = "closed"  # closed (re-check) | resolve (find employer page for an aggregator row)
    extra: dict = field(default_factory=dict)


def _cells(line: str) -> list[str]:
    parts = [c.strip() for c in line.strip().strip("|").split("|")]
    return parts


def parse_current_list(path=config.SEED_LIST) -> tuple[list[SeedRow], list[ClosedSeed]]:
    rows: list[SeedRow] = []
    closed: list[ClosedSeed] = []
    section = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            h = line.lower()
            section = "fit" if "fit your profile" in h else "poor" if "poor match" in h else "closed" if "not open" in h else None
            continue
        if section in ("fit", "poor") and line.startswith("|") and "[" in line:
            c = _cells(line)
            m = LINK.search(c[0])
            if not m:
                continue
            rest = m.group("rest")
            rows.append(SeedRow(
                section=section, title=m.group("title").strip(), url=m.group("url").strip(),
                company=c[1], location=c[2], pay=c[3], reason=c[4] if section == "poor" and len(c) > 4 else "",
                note=rest.replace("†", "").strip(), dagger="†" in rest,
            ))
        elif section == "closed" and line.startswith("- **"):
            m = re.match(r"- \*\*(?P<label>[^*]+?):\*\*\s*(?P<reason>.*)", line)
            if m:
                label = m.group("label")
                company, _, title = label.partition(", ")
                closed.append(ClosedSeed(company=company.strip(), title=title.strip(), reason=m.group("reason").strip()))
    return rows, closed


def load_watchlist(path=config.SEEDS / "watchlist.csv") -> list[Watch]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [
            Watch(
                label=r["label"], company=r["company"], method=r["method"], target=r["target"],
                title_regex=r["title_regex"], location_regex=r.get("location_regex", ""),
                note=r.get("note", ""), kind=r.get("kind", "closed"),
            )
            for r in csv.DictReader(f)
        ]
