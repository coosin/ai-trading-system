#!/usr/bin/env python3
"""
Backfill historical trade truth from exchange fills for records with zero price/fee.

Usage:
  python3 scripts/backfill_trade_truth_from_exchange.py --days 7 --limit 200
  python3 scripts/backfill_trade_truth_from_exchange.py --days 30 --limit 500 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from dotenv import load_dotenv

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


sys.path.insert(0, str(_repo_root()))

from src.modules.core.trade_history_service import TradeHistoryService
from src.modules.exchanges.okx import OKXExchange


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _load_config() -> Dict[str, Any]:
    root = _repo_root()
    load_dotenv(root / ".env")
    with open(root / "config" / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    local_yaml = root / "config" / "local.yaml"
    if local_yaml.is_file():
        with open(local_yaml, "r", encoding="utf-8") as f:
            extra = yaml.safe_load(f) or {}
        if isinstance(extra, dict):
            config.update(extra)
    return config


def _build_okx_config(config: Dict[str, Any]) -> Dict[str, Any]:
    okx_cfg = dict((((config or {}).get("exchanges") or {}).get("okx") or {}))
    okx_cfg["exchange_id"] = "okx"
    okx_cfg["api_key"] = os.getenv(str(okx_cfg.get("api_key_env") or "OKX_API_KEY"), "")
    okx_cfg["api_secret"] = os.getenv(str(okx_cfg.get("secret_env") or "OKX_SECRET"), "")
    okx_cfg["api_passphrase"] = os.getenv(str(okx_cfg.get("passphrase_env") or "OKX_PASSPHRASE"), "")
    return okx_cfg


def _aggregate_fills(fills: List[Dict[str, Any]]) -> Tuple[float, float, Optional[float]]:
    ex_pnl = 0.0
    ex_fee = 0.0
    ex_px_num = 0.0
    ex_px_den = 0.0
    for fill in fills or []:
        if not isinstance(fill, dict):
            continue
        for key in ("fillPnl", "pnl", "realizedPnl"):
            if fill.get(key) is None:
                continue
            ex_pnl += _to_float(fill.get(key))
            break
        ex_fee += _to_float(fill.get("fee"))
        fill_sz = _to_float(fill.get("fillSz") if fill.get("fillSz") is not None else fill.get("sz"))
        fill_px = _to_float(fill.get("fillPx") if fill.get("fillPx") is not None else fill.get("px"))
        if fill_sz > 0 and fill_px > 0:
            ex_px_num += fill_px * fill_sz
            ex_px_den += fill_sz
    ex_price = (ex_px_num / ex_px_den) if ex_px_den > 1e-18 else None
    return ex_pnl, ex_fee, ex_price


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    config = _load_config()
    svc = TradeHistoryService()
    if not await svc.initialize():
        print("init_failed:trade_history_service")
        return 2

    okx = OKXExchange(_build_okx_config(config))
    if not await okx.initialize():
        print("init_failed:okx_exchange")
        return 2

    start_date = datetime.now() - timedelta(days=max(1, int(args.days or 7)))
    rows = await svc.get_trade_history(start_date=start_date, limit=max(20, int(args.limit or 200)))
    candidates: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        oid = str(row.get("order_id") or "").strip()
        sym = str(row.get("symbol") or "").strip()
        if not oid or not sym:
            continue
        price = _to_float(row.get("price"))
        fee = _to_float(row.get("fee"))
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if bool(md.get("fills_enriched")) and price > 0 and fee != 0:
            continue
        if price > 0 and fee != 0:
            continue
        candidates.append(row)

    checked = 0
    matched = 0
    updated = 0
    for row in candidates[: max(1, int(args.limit or 200))]:
        checked += 1
        oid = str(row.get("order_id") or "").strip()
        sym = str(row.get("symbol") or "").strip()
        try:
            fills = await asyncio.wait_for(okx.get_swap_fills_for_order(sym, oid), timeout=3.0)
        except Exception:
            fills = []
        if not fills:
            continue
        matched += 1
        ex_pnl, ex_fee, ex_price = _aggregate_fills(fills)
        print(
            f"match order_id={oid} symbol={sym} "
            f"old_price={_to_float(row.get('price')):.8f} new_price={_to_float(ex_price):.8f} "
            f"old_fee={_to_float(row.get('fee')):.8f} new_fee={ex_fee:.8f} fills={len(fills)}"
        )
        if not args.apply:
            continue
        changed = await svc.apply_exchange_truth(
            order_id=oid,
            symbol=sym,
            exchange_pnl=ex_pnl if str(row.get("action") or "").strip().lower() in {"close", "closed"} else None,
            exchange_fee=ex_fee,
            exchange_price=ex_price,
            source="manual_backfill_script",
        )
        if changed:
            updated += 1

    await okx.cleanup()
    print(
        f"checked={checked} matched={matched} updated={updated} "
        f"mode={'apply' if args.apply else 'dry_run'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
