"""Per-channel counters and the out/run_log.md writer.

Channels call record_channel(); the HTTP client appends every request to
data/runs/<run>/http-<pid>.jsonl. write_run_log() merges both into out/run_log.md.
"""
from __future__ import annotations

import collections
import json
import os
import time
from urllib.parse import urlsplit

from . import config


def record_channel(
    name: str,
    *,
    queried: int = 0,
    candidates: int = 0,
    verified_open: int | None = None,
    kept: int | None = None,
    failures: list[str] | None = None,
    skipped: list[str] | None = None,
    notes: str = "",
) -> None:
    rec = {
        "channel": name, "queried": queried, "candidates": candidates, "verified_open": verified_open,
        "kept": kept, "failures": failures or [], "skipped": skipped or [], "notes": notes,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid(),
    }
    with open(config.run_dir() / "channels.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def load_channels() -> dict[str, dict]:
    path = config.run_dir() / "channels.jsonl"
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["channel"]] = r  # last write per channel wins
    return out


def load_http() -> list[dict]:
    recs = []
    for p in sorted(config.run_dir().glob("http-*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    pass
    return recs


def _md(s) -> str:
    return str(s if s is not None else "—").replace("|", "\\|").replace("\n", " ")


def write_run_log(extra_sections: list[tuple[str, str]] | None = None) -> str:
    chans = load_channels()
    http = load_http()
    lines = [f"# Run log {config.run_id()}", "", f"User-Agent: `{config.USER_AGENT}`", ""]

    lines += ["## Channels", "", "| Channel | Queried | Candidates | Verified open | Kept | Notes |", "|---|---:|---:|---:|---:|---|"]
    for name in sorted(chans):
        c = chans[name]
        lines.append(f"| {name} | {_md(c['queried'])} | {_md(c['candidates'])} | {_md(c['verified_open'])} | {_md(c['kept'])} | {_md(c['notes'])} |")

    skipped = [(n, s) for n, c in sorted(chans.items()) for s in c.get("skipped", [])]
    lines += ["", "## Blocked or skipped", ""]
    by_host: dict[str, set] = collections.defaultdict(set)
    for r in http:
        if r.get("blocked"):
            by_host[urlsplit(r["url"]).netloc].add(f"{r['blocked']}: {r.get('error') or ''}".strip())
    if not skipped and not by_host:
        lines.append("None.")
    for n, s in skipped:
        lines.append(f"- **{n}**: {s}")
    for host, why in sorted(by_host.items()):
        lines.append(f"- `{host}`: {'; '.join(sorted(why))}")

    fails = [r for r in http if r.get("error") and not r.get("blocked")]
    chan_fails = [(n, f) for n, c in sorted(chans.items()) for f in c.get("failures", [])]
    lines += ["", "## Failures", ""]
    if not fails and not chan_fails:
        lines.append("None.")
    for n, f in chan_fails:
        lines.append(f"- **{n}**: {f}")
    for r in fails:
        lines.append(f"- `{r['method']} {r['url']}` ({r['channel']}): {r['error']}")

    for title, body in extra_sections or []:
        lines += ["", f"## {title}", "", body]

    # per-host summary, then every request
    per_host = collections.Counter(urlsplit(r["url"]).netloc for r in http)
    live = sum(1 for r in http if not r.get("cache") and not r.get("blocked"))
    lines += ["", "## Requests by host", "", f"{len(http)} requests logged ({live} live, {len(http) - live} cache hits or blocks).", "",
              "| Host | Requests |", "|---|---:|"]
    for h, n in per_host.most_common():
        lines.append(f"| {h} | {n} |")
    lines += ["", "<details><summary>Every endpoint hit this run</summary>", "", "| Time | Channel | Method | URL | Status | Cache |", "|---|---|---|---|---|---|"]
    for r in sorted(http, key=lambda r: r["ts"]):
        st = r.get("status") if r.get("status") is not None else (r.get("blocked") or "error")
        lines.append(f"| {r['ts'][11:]} | {r['channel']} | {r['method']} | {_md(r['url'])} | {st} | {'hit' if r.get('cache') else ''} |")
    lines += ["", "</details>", ""]
    path = config.OUT / "run_log.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
