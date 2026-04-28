#!/usr/bin/env python3
"""
Unified verification entrypoint.

Subcommands:
- trading: execution/SLTP/learning acceptance checks
- network: production network baseline checks
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def _run(script_name: str, extra_args: list[str]) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(here, script_name)
    cmd = [sys.executable, script, *extra_args]
    p = subprocess.run(cmd, check=False)
    return int(p.returncode or 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("trading", help="Run trading full checks")
    t.add_argument("--base-url", default="http://127.0.0.1:8000")
    t.add_argument("--limit-events", type=int, default=20)
    t.add_argument("--seed-n", type=int, default=8)
    t.add_argument("--seed-symbol", default="BTC/USDT/SWAP")

    n = sub.add_parser("network", help="Run production network baseline checks")
    n.add_argument("--apply", action="store_true")
    n.add_argument("--check-only", action="store_true")

    args = ap.parse_args()
    if args.cmd == "trading":
        return _run(
            "trading_exec_fullcheck.py",
            [
                "--base-url",
                args.base_url,
                "--limit-events",
                str(args.limit_events),
                "--seed-n",
                str(args.seed_n),
                "--seed-symbol",
                args.seed_symbol,
            ],
        )
    return _run(
        "production_network_baseline.py",
        (["--apply"] if args.apply else []) + (["--check-only"] if args.check_only else []),
    )


if __name__ == "__main__":
    raise SystemExit(main())

