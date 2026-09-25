"""CLI: python -m radar <command>

  verify-seeds              Phase 1: re-check seeds/current_list.md -> out/seed_verification_<date>.md
  boards [--company NAME]   Phase 2: detect ATS for every registry company, pull full boards
  discover CHANNEL          Phase 3: run one discovery channel (module radar/discover/CHANNEL.py)
  import-leads FILE         Append leads from a JSONL file (web-search results gathered by Claude)
  refresh                   Phases 1-5 end to end
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify-seeds", help="Phase 1: re-verify the seed list")
    b = sub.add_parser("boards", help="Phase 2: detect ATS and pull full boards")
    b.add_argument("--company", action="append", help="limit to these registry companies (repeatable)")
    b.add_argument("--redetect", action="store_true", help="probe ATS again even when already detected")
    d = sub.add_parser("discover", help="Phase 3: run one discovery channel")
    d.add_argument("channel")
    il = sub.add_parser("import-leads", help="append leads from a JSONL file")
    il.add_argument("file")
    il.add_argument("--source", help="override the source field on every lead")
    rf = sub.add_parser("refresh", help="phases 1-5 end to end")
    rf.add_argument("--skip-discovery", action="store_true", help="reuse leads already gathered today")
    rf.add_argument("--channels", nargs="*", help="discovery channels to run (default: all)")
    sub.add_parser("score", help="phases 4-5 only, reusing today's seed check, board pulls and leads")
    sub.add_parser("apply-judgments", help="merge data/judgments/results/*.json into data/judgments.jsonl")
    args = ap.parse_args(argv)

    if args.cmd in ("refresh", "score"):
        from . import pipeline

        if args.cmd == "refresh":
            summary = pipeline.refresh(args.skip_discovery, args.channels)
        else:
            from . import phase1

            with __import__("radar.http", fromlist=["channel"]).channel("phase1:seed-verify"):
                results, closed = phase1.verify_seeds()
            summary = pipeline.finish(results, closed)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "apply-judgments":
        from .phase4 import apply_judgments

        print(f"applied {apply_judgments()} judgments")
        return 0

    if args.cmd == "verify-seeds":
        from . import phase1, runlog

        results, closed = phase1.verify_seeds()
        path = phase1.write_report(results, closed)
        runlog.write_run_log()
        print(f"wrote {path}")
        for r in results:
            print(f"{r.status:10} {r.row.company[:28]:28} {r.row.title[:60]:60} {r.posting.pay_display if r.posting else ''}")
        for c in closed:
            print(f"{c.status:13} {c.label[:80]}")

    elif args.cmd == "boards":
        from . import phase2, runlog

        summary = phase2.run(companies=args.company, redetect=args.redetect)
        runlog.write_run_log()
        print(json.dumps(summary, indent=2))

    elif args.cmd == "discover":
        from .http import channel

        mod = importlib.import_module(f"radar.discover.{args.channel}")
        with channel(f"discover:{args.channel}"):
            result = mod.run()
        print(json.dumps(result, indent=2, default=str))

    elif args.cmd == "import-leads":
        from .leads import add_leads
        from .models import Lead

        leads = []
        with open(args.file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    if args.source:
                        d["source"] = args.source
                    leads.append(Lead(**{k: v for k, v in d.items() if k in Lead.model_fields}))
        print(f"added {add_leads(leads)} of {len(leads)} leads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
