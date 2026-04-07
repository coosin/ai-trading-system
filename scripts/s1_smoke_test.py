#!/usr/bin/env python3
"""
S1 链路透测：单元测试 +（可选）OKX 只读实盘检查。

默认不做任何下单。若需真实下单，须同时传入：
  --confirm-live-write --size 1 --symbol BTC/USDT --side long

用法：
  cd /path/to/.openclaw-trading
  python3 scripts/s1_smoke_test.py
  OKX_API_KEY=... OKX_SECRET=... OKX_PASSPHRASE=... python3 scripts/s1_smoke_test.py --read-exchange
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def run_unit_tests() -> int:
    tests = [
        "tests/unit/test_execution_gateway.py",
        "tests/unit/test_stop_loss_exchange_sync.py",
        "tests/unit/test_stop_loss_gateway_close.py",
    ]
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short", *tests]
    print("→", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(REPO))


async def read_exchange_smoke() -> int:
    from src.modules.exchanges.okx import OKXExchange

    key = os.getenv("OKX_API_KEY", "")
    secret = os.getenv("OKX_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")
    if not (key and secret and passphrase):
        print("跳过交易所只读检查：未设置 OKX_API_KEY / OKX_SECRET / OKX_PASSPHRASE")
        return 0

    testnet = os.getenv("OKX_TESTNET", "").lower() in ("1", "true", "yes")
    ex = OKXExchange(
        {
            "api_key": key,
            "api_secret": secret,
            "api_passphrase": passphrase,
            "testnet": testnet,
        }
    )
    await ex.initialize()
    try:
        bal = await ex.get_balance()
        print("余额键示例:", list(bal.keys())[:8] if isinstance(bal, dict) else type(bal))
        pos = await ex.get_positions()
        print("持仓条数:", len(pos or []))
        tick = await ex.get_ticker("BTC-USDT-SWAP")
        print("BTC 永续 ticker:", tick.get("last") if isinstance(tick, dict) else tick)
        print("✅ 交易所只读检查完成（未下单）")
        return 0
    finally:
        await ex.cleanup()


async def optional_live_open(args: argparse.Namespace) -> int:
    if not args.confirm_live_write:
        print("拒绝真实下单：缺少 --confirm-live-write")
        return 2
    from src.modules.exchanges.okx import OKXExchange

    key = os.getenv("OKX_API_KEY", "")
    secret = os.getenv("OKX_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")
    if not (key and secret and passphrase):
        print("缺少 API 环境变量")
        return 2

    testnet = os.getenv("OKX_TESTNET", "").lower() in ("1", "true", "yes")
    ex = OKXExchange(
        {
            "api_key": key,
            "api_secret": secret,
            "api_passphrase": passphrase,
            "testnet": testnet,
        }
    )
    await ex.initialize()
    try:
        lev = int(args.leverage)
        print(
            f"⚠️ 即将真实开仓 {args.symbol} {args.side} size={args.size} leverage={lev} testnet={testnet}"
        )
        await ex.set_leverage(args.symbol, lev, "cross")
        res = await ex.open_swap_position(
            args.symbol, args.side, float(args.size), lev, None, "cross"
        )
        print("结果:", res)
        return 0 if isinstance(res, dict) and res.get("success") else 1
    finally:
        await ex.cleanup()


def main() -> int:
    p = argparse.ArgumentParser(description="S1 smoke: tests + optional exchange")
    p.add_argument("--skip-pytest", action="store_true")
    p.add_argument("--read-exchange", action="store_true", help="只读：余额/持仓/行情（需 env 密钥）")
    p.add_argument("--confirm-live-write", action="store_true", help="允许真实开仓（危险）")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--side", default="long", choices=["long", "short"])
    p.add_argument("--size", type=float, default=1.0)
    p.add_argument("--leverage", type=int, default=3)
    args = p.parse_args()

    if not args.skip_pytest:
        rc = run_unit_tests()
        if rc != 0:
            return rc

    if args.read_exchange:
        return asyncio.run(read_exchange_smoke())

    if args.confirm_live_write:
        return asyncio.run(optional_live_open(args))

    print("完成（仅 pytest）。加 --read-exchange 做 OKX 只读实测，或显式传入开仓参数做真实下单。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
