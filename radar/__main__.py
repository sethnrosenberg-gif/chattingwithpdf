"""CLI: python -m radar <command>

  verify-seeds   Phase 1 only: re-check seeds/current_list.md, write out/seed_verification_<date>.md
  refresh        Phases 1-5 end to end (see radar/pipeline.py)
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify-seeds", help="Phase 1: re-verify the seed list")
    args = ap.parse_args(argv)

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
