#!/usr/bin/env python3
"""
Unified verification entrypoint.

Subcommands:
- trading: execution/SLTP/learning acceptance checks
- network: production network baseline checks
- trading-models: CLIProxyAPI trading alias acceptance checks
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


def _run_pytest(extra_args: list[str]) -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pytest_bin = os.path.join(repo_root, ".venv", "bin", "pytest")
    if not os.path.exists(pytest_bin):
        pytest_bin = "pytest"
    env = dict(os.environ)
    env["PYTHONPATH"] = repo_root + (
        (os.pathsep + env["PYTHONPATH"]) if env.get("PYTHONPATH") else ""
    )
    cmd = [pytest_bin, *extra_args]
    p = subprocess.run(cmd, check=False, cwd=repo_root, env=env)
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
    n.add_argument(
        "--quick",
        action="store_true",
        help="透传 --quick：缩短探针轮次/超时（与本机同网络栈；失败仍 exit 2）",
    )

    g = sub.add_parser("trading-gates", help="Run microstructure gate regression tests")
    g.add_argument("--kexpr", default="microstructure")

    m = sub.add_parser("trading-models", help="Validate CLIProxyAPI trading logical aliases")
    m.add_argument("--base-url", default="http://127.0.0.1:8317/v1")
    m.add_argument("--api-key", default="")
    m.add_argument("--api-key-env", default="CLI_PROXY_API_KEY")
    m.add_argument("--timeout", type=float, default=30.0)
    m.add_argument("--skip-completions", action="store_true")

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
    if args.cmd == "trading-gates":
        return _run_pytest(
            [
                "-q",
                "tests/test_ai_trading_engine.py",
                "-k",
                str(args.kexpr),
            ]
        )
    if args.cmd == "trading-models":
        extra_args = [
            "--base-url",
            args.base_url,
            "--api-key-env",
            args.api_key_env,
            "--timeout",
            str(args.timeout),
        ]
        if args.api_key:
            extra_args.extend(["--api-key", args.api_key])
        if args.skip_completions:
            extra_args.append("--skip-completions")
        return _run("validate_trading_model_aliases.py", extra_args)
    return _run(
        "production_network_baseline.py",
        (["--apply"] if args.apply else [])
        + (["--check-only"] if args.check_only else [])
        + (["--quick"] if getattr(args, "quick", False) else []),
    )


if __name__ == "__main__":
    raise SystemExit(main())
