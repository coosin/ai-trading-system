#!/usr/bin/env python3
"""
SR/SLTP simulation test (no real exchange orders).

Purpose:
- Validate SR near resistance/support triggers
- Validate partial-take-profit + breakeven lock counters/events
- No real orders: execute_exchange_on_trigger = False

Run:
  python scripts/sltp_sr_simtest.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import os
import sys


class MockExchange:
    async def get_klines(self, symbol: str, interval: str = "1H", limit: int = 50):
        # Create a resistance at 110 and support at 90 (excluding last bar).
        bars = []
        for i in range(limit):
            bars.append(
                {
                    "timestamp": i,
                    "open": 100.0,
                    "high": 110.0 if i < limit - 2 else 105.0,
                    "low": 90.0 if i < limit - 2 else 95.0,
                    "close": 100.0,
                    "volume": 1.0,
                }
            )
        return bars

    async def get_order_book(self, symbol: str, depth: int = 10):
        return None


async def run_one(side: str):
    # Ensure project root is importable when running as a standalone script.
    this_dir = os.path.dirname(os.path.abspath(__file__))
    proj_root = os.path.abspath(os.path.join(this_dir, ".."))
    if proj_root not in sys.path:
        sys.path.insert(0, proj_root)

    from src.modules.core.stop_loss_take_profit import StopLossTakeProfitManager, StopLossTakeProfitConfig

    cfg = StopLossTakeProfitConfig()
    cfg.execute_exchange_on_trigger = False  # IMPORTANT: no real close
    cfg.sr_exit_enable = True
    cfg.sr_partial_tp_trigger_pnl = 0.01
    cfg.sr_partial_close_ratio = 0.25
    cfg.sr_breakeven_lock_pct = 0.0015

    mgr = StopLossTakeProfitManager(cfg)
    mgr.set_exchange(MockExchange())

    # Create a synthetic order and move price near resistance/support with pnl>trigger
    entry = 100.0
    if side == "long":
        # pnl 2% => 102, near resistance=110 (within 0.35%? no) so we move close to 109.8 (pnl 9.8%)
        prices = [101.2, 103.0, 107.0, 109.7, 109.8]
    else:
        # short: price drops to 90.3 near support=90 with pnl ~9.7%
        prices = [99.0, 97.0, 94.0, 90.6, 90.3]

    order = await mgr.create_order(
        symbol="TEST/USDT/SWAP",
        side=side,
        entry_price=entry,
        quantity=10.0,
        stop_loss_config=None,
        take_profit_config=None,
        metadata={"trace_id": f"sim-{side}-{datetime.now().timestamp()}"},
    )

    for px in prices:
        order.current_price = float(px)
        # This is where SR logic lives.
        await mgr._dynamic_market_adjust(order, float(px))

    return mgr.get_stats()


async def main():
    s_long = await run_one("long")
    s_short = await run_one("short")
    # Show SR counters
    print("LONG_SR", {k: s_long.get(k) for k in s_long.keys() if str(k).startswith("sr_")})
    print("SHORT_SR", {k: s_short.get(k) for k in s_short.keys() if str(k).startswith("sr_")})
    print("LONG_events", (s_long.get("sr_recent_events") or [])[-3:])
    print("SHORT_events", (s_short.get("sr_recent_events") or [])[-3:])


if __name__ == "__main__":
    asyncio.run(main())

