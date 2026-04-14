#!/usr/bin/env python3
"""
执行巡检 + 生成摘要 + 推送 Telegram。
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from urllib import parse, request


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text[:3500],
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = request.Request(url, data=payload, method="POST")
    with request.urlopen(req, timeout=15) as resp:
        if resp.status != 200:
            raise RuntimeError(f"telegram_send_failed_http_{resp.status}")


def _read_env_file_value(key: str, env_file: str = ".env") -> str:
    p = Path(env_file)
    if not p.exists():
        return ""
    try:
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() != key:
                continue
            # 去掉行内注释
            v = v.split(" #", 1)[0].strip().strip('"').strip("'")
            return v
    except Exception:
        return ""
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="巡检+日报+TG推送")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--iterations", type=int, default=1, help="每次执行巡检轮数")
    parser.add_argument("--interval-sec", type=int, default=5, help="巡检轮间隔")
    parser.add_argument("--thresholds", default="docs/system-monitor-thresholds.example.json")
    parser.add_argument("--probe-output", default="logs/system_probe_report.jsonl")
    parser.add_argument("--summary-output", default="logs/system_probe_daily_summary.md")
    parser.add_argument("--bot-token", default=os.getenv("TELEGRAM_BOT_TOKEN", ""))
    parser.add_argument("--chat-id", default=os.getenv("TELEGRAM_CHAT_ID", ""))
    args = parser.parse_args()

    bot_token = args.bot_token or _read_env_file_value("TELEGRAM_BOT_TOKEN")
    chat_id = args.chat_id or _read_env_file_value("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise SystemExit("缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID")

    _run(
        [
            "python3",
            "scripts/continuous_system_probe.py",
            "--base-url",
            args.base_url,
            "--iterations",
            str(args.iterations),
            "--interval-sec",
            str(args.interval_sec),
            "--thresholds",
            args.thresholds,
            "--output",
            args.probe_output,
        ]
    )

    _run(
        [
            "python3",
            "scripts/system_probe_daily_summary.py",
            "--input",
            args.probe_output,
            "--output",
            args.summary_output,
        ]
    )

    summary = Path(args.summary_output).read_text(encoding="utf-8")
    msg = "📊 系统巡检日报\n\n" + summary
    _send_telegram(bot_token, chat_id, msg)
    print("ok: probe + summary + telegram pushed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

