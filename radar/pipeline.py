"""`python -m radar refresh`: phases 1-5 end to end."""
from __future__ import annotations

import json
import os
import smtplib
import subprocess
import sys
from email.message import EmailMessage

from . import config, output, phase1, phase2, phase4, runlog
from .http import channel, client

CHANNELS = ["public_sector", "official_apis", "hn", "commoncrawl", "websearch", "wayback"]


def run_discovery(channels: list[str]) -> dict[str, int]:
    """Each channel runs as its own process, in parallel; the shared rate limiter keeps hosts at 1 req/s."""
    env = {**os.environ, "RADAR_RUN_ID": config.run_id(), "PYTHONIOENCODING": "utf-8"}
    procs = {}
    for ch in channels:
        log = open(config.run_dir() / f"discover_{ch}.out", "w", encoding="utf-8")
        procs[ch] = (subprocess.Popen([sys.executable, "-m", "radar", "discover", ch], cwd=config.ROOT, env=env,
                                      stdout=log, stderr=subprocess.STDOUT), log)
    codes = {}
    for ch, (p, log) in procs.items():
        codes[ch] = p.wait()
        log.close()
    return codes


def _found_elsewhere(row, posts) -> str | None:
    """A seed row we couldn't reach directly may have been verified through another official page."""
    import re

    from .phase1 import same_role
    from .textutil import norm_company

    refs = set(re.findall(r"\d{4}", row.url))
    for p in posts:
        if norm_company(p.company)[:6] != norm_company(row.company)[:6]:
            continue
        if (refs and any(ref in p.title or ref in p.url for ref in refs)) or same_role(row.title, p.title):
            return f"[{p.title}]({p.url})"
    return None


def closed_notes(results, closed, posts=()) -> list[str]:
    notes = []
    for r in results:
        if r.status != "open" and (alt := _found_elsewhere(r.row, posts)):
            notes.append(f"**{r.row.company}, {r.row.title}:** the original link couldn't be verified ({r.evidence}), "
                         f"but the same posting was verified at {alt} and is listed above.")
            continue
        if r.status == "closed":
            notes.append(f"**{r.row.company}, {r.row.title}:** closed. {r.evidence}.")
        elif r.status == "unverified":
            notes.append(f"**{r.row.company}, {r.row.title}:** couldn't verify, so it's left off. {r.evidence}.")
    for c in closed:
        if c.status != "reopened":
            notes.append(f"**{c.label}:** {'still closed' if c.status == 'still closed' else 'couldn’t check'}. {c.evidence}.")
    return notes


def digest(summary: dict) -> str | None:
    lines = [f"Job radar {config.run_id()}: {summary['new_fit']} new fit rows"] + summary["top_new_fits"]
    body = "\n".join(lines)
    if topic := config.env("NTFY_TOPIC"):
        with channel("digest"):
            # the user's own opt-in notification topic, so no robots check
            client().post_json("https://ntfy.sh/", {"topic": topic, "title": "Job radar", "message": body},
                               use_cache=False, check_robots=False)
        return "ntfy"
    if (host := config.env("SMTP_HOST")) and (to := config.env("DIGEST_TO")):
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = lines[0], config.env("SMTP_USER") or to, to
        msg.set_content(body)
        with smtplib.SMTP(host, int(config.env("SMTP_PORT") or 587)) as s:
            s.starttls()
            if config.env("SMTP_USER"):
                s.login(config.env("SMTP_USER"), config.env("SMTP_PASSWORD") or "")
            s.send_message(msg)
        return "email"
    return None


def finish(results, closed, verify_leads: bool = True) -> dict:
    with channel("phase4:verify-score"):
        posts, stats = phase4.run(verify_leads)
    batches = phase4.export_judgments(posts)
    summary = output.write(posts, closed_notes(results, closed, posts), stats)
    summary["judgment_batches_pending"] = batches
    output.dump_stats(stats)
    for src, s in stats.get("by_source", {}).items():
        chans = runlog.load_channels()
        name = next((c for c in chans if c.endswith(src) or src.startswith(c.split(":")[-1])), f"discover:{src}")
        prev = chans.get(name, {})
        runlog.record_channel(name, queried=prev.get("queried", 0), candidates=prev.get("candidates", s["leads"]),
                              verified_open=s["verified_open"], kept=sum(1 for p in posts if any(x.startswith(src) for x in p.sources)),
                              failures=prev.get("failures"), skipped=prev.get("skipped"), notes=prev.get("notes", ""))
    runlog.record_channel("phase2:boards", **{k: v for k, v in runlog.load_channels().get("phase2:boards", {}).items()
                                               if k in ("queried", "candidates", "failures", "skipped", "notes")},
                          verified_open=stats["boards"], kept=sum(1 for p in posts if any(x.startswith("board:") for x in p.sources)))
    fits_ok = summary["fit"] >= 11
    extra = [("Phase 4 verification", "```\n" + json.dumps({k: v for k, v in stats.items()}, indent=1, default=str) + "\n```"),
             ("Fit-row check", f"{summary['fit']} verified fit rows vs 11 in the seed list. " +
              ("Meets the bar." if fits_ok else "Below the seed count; see closed and unverifiable seed rows above for why."))]
    runlog.write_run_log(extra)
    return summary


def refresh(skip_discovery: bool = False, channels: list[str] | None = None) -> dict:
    with channel("phase1:seed-verify"):
        results, closed = phase1.verify_seeds()
    phase1.write_report(results, closed)
    if not skip_discovery:
        run_discovery(channels or CHANNELS)
    with channel("phase2:boards"):
        phase2.run()
    summary = finish(results, closed)
    summary["digest"] = digest(summary)
    return summary
