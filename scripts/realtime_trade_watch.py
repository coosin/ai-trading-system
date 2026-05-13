#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, timeout: float = 8.0) -> Tuple[Optional[Any], Optional[str]]:
    try:
        with urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw), None
    except HTTPError as e:
        return None, f"http_error:{e.code}"
    except URLError as e:
        return None, f"url_error:{e.reason}"
    except Exception as e:
        return None, f"error:{type(e).__name__}:{e}"


def dig(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _symbol_endpoint(symbol: str) -> str:
    return f"/api/v1/market/symbol/{quote(symbol, safe='')}?include_snapshot=true"


def collect(base_url: str, symbols: List[str]) -> Dict[str, Any]:
    endpoints = {
        "acceptance": "/api/v1/system/acceptance",
        "profit": "/api/v1/modules/profit/ops-overview",
        "stop_loss": "/api/v1/modules/stop-loss/stats",
        "risk": "/api/v1/modules/risk/status",
        "market_state": "/api/v1/monitoring/proactive-ai/market-state",
        "alerts": "/api/v1/monitoring/alerts",
        "trades_recent": "/api/v1/trades/recent",
        "engine_status": "/api/v1/modules/trading/engine/status",
    }
    payload: Dict[str, Any] = {"ts": now_utc(), "base_url": base_url, "sources": {}, "errors": {}}
    for name, path in endpoints.items():
        data, err = fetch_json(f"{base_url}{path}")
        if err:
            payload["errors"][name] = err
        else:
            payload["sources"][name] = data
    symbol_views: Dict[str, Any] = {}
    for symbol in symbols:
        data, err = fetch_json(f"{base_url}{_symbol_endpoint(symbol)}", timeout=12.0)
        key = f"symbol_view:{symbol}"
        if err:
            payload["errors"][key] = err
            continue
        symbol_views[symbol] = data
    payload["sources"]["symbol_views"] = symbol_views
    return payload


def summarize(snapshot: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    src = snapshot.get("sources", {})
    acceptance = src.get("acceptance", {}) or {}
    profit = src.get("profit", {}) or {}
    stop_loss = src.get("stop_loss", {}) or {}
    risk = src.get("risk", {}) or {}
    market = src.get("market_state", {}) or {}
    alerts = src.get("alerts", []) or []
    recent = src.get("trades_recent", {}) or {}
    engine_status = src.get("engine_status", {}) or {}
    symbol_views = src.get("symbol_views", {}) if isinstance(src.get("symbol_views"), dict) else {}

    verdict = dig(acceptance, "verdict", default="unknown")
    running_modules = dig(acceptance, "system_status", "running_modules", default="?")
    risk_level = risk.get("risk_level", "unknown")
    position_count = dig(risk, "last_check", "position_count", default="?")
    equity = num(dig(risk, "last_check", "total_equity", default=0.0))
    trend = market.get("trend", "unknown")
    vol_regime = market.get("volatility_regime", "unknown")
    liquidity = market.get("liquidity", "unknown")

    guard_stats = dig(profit, "execution_guards", "stats", default={}) or {}
    regime_rows = dig(profit, "profit_attribution", "regime", default=[]) or []
    readiness = bool(dig(profit, "profit_attribution", "health", "readiness", "ready_for_regime_tuning", default=False))
    tp_stats = stop_loss.get("stats", {}) if isinstance(stop_loss.get("stats"), dict) else {}

    active_alerts = len(alerts) if isinstance(alerts, list) else 0
    rr_rej = int(num(guard_stats.get("rr_rejected", 0), 0))
    sr_rej = int(num(guard_stats.get("sr_timing_rejected", 0), 0))
    open_evidence_rej = int(num(guard_stats.get("open_evidence_rejected", 0), 0))
    tp_suppressed = int(num(tp_stats.get("tp_net_edge_suppressed", 0), 0))
    active_orders = int(num(tp_stats.get("active_orders", 0), 0))

    regime_best = None
    regime_worst = None
    if isinstance(regime_rows, list) and regime_rows:
        ordered = sorted(
            [r for r in regime_rows if isinstance(r, dict)],
            key=lambda r: num(r.get("total_pnl", 0.0), 0.0),
        )
        if ordered:
            regime_worst = ordered[0]
            regime_best = ordered[-1]

    trade_rows = recent.get("trades", []) if isinstance(recent.get("trades"), list) else []
    latest_trade = trade_rows[0] if trade_rows and isinstance(trade_rows[0], dict) else {}
    latest_trade_id = str(latest_trade.get("trade_id") or latest_trade.get("order_id") or "")
    latest_trade_pnl = num(latest_trade.get("pnl", 0.0), 0.0)
    latest_trade_reason = str(latest_trade.get("reasoning") or "")

    prev_latest_trade_id = ""
    prev_tp_suppressed = 0
    if prev:
        prev_latest_trade_id = str(dig(prev, "analysis", "latest_trade_id", default=""))
        prev_tp_suppressed = int(num(dig(prev, "analysis", "tp_net_edge_suppressed", default=0), 0))

    events: List[str] = []
    if latest_trade_id and latest_trade_id != prev_latest_trade_id:
        events.append(f"new_trade={latest_trade.get('symbol','?')} pnl={latest_trade_pnl:.4f} reason={latest_trade_reason}")
    if tp_suppressed > prev_tp_suppressed:
        events.append(f"tp_edge_suppressed+{tp_suppressed - prev_tp_suppressed}")
    if active_alerts > 0:
        events.append(f"alerts={active_alerts}")

    engine_note = ""
    if isinstance(engine_status, dict):
        eng = engine_status.get("engine") if isinstance(engine_status.get("engine"), dict) else {}
        eng_status = str(eng.get("status") or "").strip().lower()
        exchange_connected = bool(engine_status.get("exchange_connected"))
        engine_live = eng_status in {"connected", "running", "ok", "healthy"}
        engine_note = f"engine={'on' if engine_live else 'off'} exch={'on' if exchange_connected else 'off'}"

    line = (
        f"[{snapshot['ts']}] verdict={verdict} modules={running_modules} {engine_note} "
        f"risk={risk_level} pos={position_count} equity={equity:.2f} "
        f"market={trend}/{vol_regime}/{liquidity} "
        f"guards(rr={rr_rej},sr={sr_rej},evidence={open_evidence_rej}) "
        f"sltp(active={active_orders},tp_suppressed={tp_suppressed}) "
        f"regime_ready={'yes' if readiness else 'no'}"
    )
    if regime_best:
        line += f" best={regime_best.get('regime')}:{num(regime_best.get('total_pnl',0.0)):.2f}"
    if regime_worst:
        line += f" worst={regime_worst.get('regime')}:{num(regime_worst.get('total_pnl',0.0)):.2f}"
    if events:
        line += " events=" + ";".join(events)

    symbol_summaries: List[Dict[str, Any]] = []
    symbol_line_parts: List[str] = []
    for symbol, payload in symbol_views.items():
        if not isinstance(payload, dict):
            continue
        view = payload.get("view") if isinstance(payload.get("view"), dict) else {}
        prov = str(view.get("provenance") or "?")
        trend_s = str(view.get("trend") or "?")
        bias_s = str(view.get("action_bias") or "?")
        q_s = view.get("quality_score")
        atr_s = view.get("atr_pct_1h")
        degraded = bool(payload.get("degraded"))
        symbol_summaries.append(
            {
                "symbol": symbol,
                "trend": trend_s,
                "bias": bias_s,
                "quality_score": q_s,
                "atr_pct_1h": atr_s,
                "provenance": prov,
                "degraded": degraded,
                "message": payload.get("message"),
            }
        )
        q_text = "-" if q_s is None else f"{num(q_s):.2f}"
        atr_text = "-" if atr_s is None else f"{num(atr_s):.4f}"
        deg_mark = "!" if degraded else ""
        symbol_line_parts.append(f"{symbol}:{trend_s}/{bias_s}@q{q_text}/atr{atr_text}/{prov}{deg_mark}")
    if symbol_line_parts:
        line += " symbols=" + ",".join(symbol_line_parts[:4])

    analysis = {
        "verdict": verdict,
        "running_modules": running_modules,
        "risk_level": risk_level,
        "position_count": position_count,
        "equity": equity,
        "trend": trend,
        "volatility_regime": vol_regime,
        "liquidity": liquidity,
        "rr_rejected": rr_rej,
        "sr_timing_rejected": sr_rej,
        "open_evidence_rejected": open_evidence_rej,
        "tp_net_edge_suppressed": tp_suppressed,
        "active_orders": active_orders,
        "active_alerts": active_alerts,
        "regime_ready": readiness,
        "best_regime": regime_best,
        "worst_regime": regime_worst,
        "latest_trade_id": latest_trade_id,
        "latest_trade": latest_trade,
        "events": events,
        "symbol_summaries": symbol_summaries,
    }
    return line, analysis


def main() -> int:
    parser = argparse.ArgumentParser(description="Realtime trading loop watcher")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--out", default="/home/cool/ai-trading-system/runtime/realtime_watch.jsonl")
    parser.add_argument("--summary-out", default="/home/cool/ai-trading-system/runtime/realtime_watch.latest.json")
    parser.add_argument("--iterations", type=int, default=0, help="0 means forever")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT")
    args = parser.parse_args()

    out_path = Path(args.out)
    latest_path = Path(args.summary_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.parent.mkdir(parents=True, exist_ok=True)

    prev: Optional[Dict[str, Any]] = None
    count = 0
    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    while True:
        count += 1
        snapshot = collect(args.base_url, symbols)
        summary_line, analysis = summarize(snapshot, prev)
        snapshot["analysis"] = analysis
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
        latest_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(summary_line, flush=True)
        prev = snapshot
        if args.iterations and count >= args.iterations:
            return 0
        time.sleep(max(1.0, float(args.interval)))


if __name__ == "__main__":
    sys.exit(main())
