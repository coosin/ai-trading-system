#!/usr/bin/env python3
"""
按时间窗口汇总 trades.jsonl（已实现盈亏与手续费），用于「优化后」基线复盘。

不修改、不删除账本；只读 JSONL。默认路径：<repo>/data/trade_history/trades.jsonl

示例（优化后约 12 小时窗口，UTC）:
  python3 scripts/trade_history_window_report.py \\
    --start 2026-05-09T20:00:00+00:00 \\
    --end   2026-05-10T08:00:00+00:00
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    t = str(s).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def row_pnl_fee_op(r: Dict[str, Any]) -> Tuple[float, float, str]:
    md = r.get("metadata") or {}
    raw = md.get("raw") or {}
    g = md.get("gateway") or {}
    op = str(g.get("op") or "").lower()
    pnl = float(r.get("pnl") or 0)
    fee = float(r.get("fee") or 0)
    if raw.get("realizedPnl") is not None:
        pnl = float(raw.get("realizedPnl") or pnl)
    if raw.get("pnl") is not None and op == "close":
        pnl = float(raw.get("pnl"))
    if raw.get("fee") is not None:
        fee = float(raw.get("fee"))
    return pnl, fee, op


def sym_key(s: Any) -> str:
    x = str(s or "").upper().replace("-SWAP", "").replace("/SWAP", "")
    return x.split(":")[0] if ":" in x else x


def default_jsonl_path() -> Path:
    return repo_root() / "data" / "trade_history" / "trades.jsonl"


def load_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    with path.open(encoding="utf-8") as f:
        for i, ln in enumerate(f, 1):
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError as e:
                print(f"WARN: skip line {i}: {e}", file=sys.stderr)
    return rows


def summarize(
    rows: List[Dict[str, Any]],
    start: datetime,
    end: datetime,
) -> Dict[str, Any]:
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    def in_win(ts: datetime) -> bool:
        return start <= ts < end

    n_open = n_close = 0
    total_pnl = 0.0
    total_fee = 0.0
    wins = losses = 0
    by_sym: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"pnl": 0.0, "fee": 0.0, "closes": 0, "opens": 0, "wins": 0, "loss": 0}
    )
    open_reasons = Counter()
    close_reasons = Counter()

    for r in rows:
        ts = parse_ts(r.get("timestamp"))
        if ts is None or not in_win(ts):
            continue
        pnl, fee, op = row_pnl_fee_op(r)
        sk = sym_key(r.get("symbol"))
        md = r.get("metadata") or {}
        g = md.get("gateway") or {}

        if op == "close":
            n_close += 1
            by_sym[sk]["closes"] += 1
            by_sym[sk]["pnl"] += pnl
            by_sym[sk]["fee"] += fee
            total_pnl += pnl
            total_fee += fee
            if pnl > 1e-9:
                by_sym[sk]["wins"] += 1
                wins += 1
            elif pnl < -1e-9:
                by_sym[sk]["loss"] += 1
                losses += 1
            close_reasons[str(r.get("reasoning") or g.get("reason") or "?")] += 1
        elif op == "open":
            n_open += 1
            by_sym[sk]["opens"] += 1
            by_sym[sk]["fee"] += fee
            total_fee += fee
            open_reasons[str(r.get("reasoning") or g.get("reason") or "?")] += 1

    denom = wins + losses
    win_rate = (wins / denom) if denom else None

    gross_w = sum(v["pnl"] for v in by_sym.values() if v["pnl"] > 0)
    gross_l = -sum(v["pnl"] for v in by_sym.values() if v["pnl"] < 0)
    pf = (gross_w / gross_l) if gross_l > 1e-9 else None

    worst = sorted(
        [{"symbol": k, **{x: v[x] for x in ("pnl", "fee", "closes", "opens", "wins", "loss")}} for k, v in by_sym.items() if v["closes"]],
        key=lambda x: x["pnl"],
    )

    return {
        "window_utc": {"start": start.isoformat(), "end": end.isoformat()},
        "opens": n_open,
        "closes": n_close,
        "realized_pnl_usdt": round(total_pnl, 6),
        "fees_usdt": round(total_fee, 6),
        "net_pnl_plus_fees_usdt": round(total_pnl + total_fee, 6),
        "close_win_rate": (round(win_rate, 4) if win_rate is not None else None),
        "closes_wins": wins,
        "closes_losses": losses,
        "profit_factor": (round(pf, 6) if pf is not None else None),
        "open_reason_top": open_reasons.most_common(12),
        "close_reason_top": close_reasons.most_common(12),
        "by_symbol_closes_sorted_worst_pnl": worst[:20],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Trade history window report (read-only)")
    ap.add_argument("--start", required=True, help="ISO8601 start (inclusive), e.g. 2026-05-09T20:00:00+00:00")
    ap.add_argument("--end", required=True, help="ISO8601 end (exclusive), e.g. 2026-05-10T08:00:00+00:00")
    ap.add_argument(
        "--file",
        default="",
        help="Path to trades.jsonl (default: <repo>/data/trade_history/trades.jsonl)",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON only")
    args = ap.parse_args()

    start = parse_ts(args.start)
    end = parse_ts(args.end)
    if start is None or end is None:
        print("ERROR: invalid --start or --end", file=sys.stderr)
        sys.exit(2)
    if end <= start:
        print("ERROR: --end must be after --start", file=sys.stderr)
        sys.exit(2)

    path = Path(args.file) if args.file else default_jsonl_path()
    rows = load_rows(path)
    out = summarize(rows, start, end)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print("TradeHistory window report (read-only)")
    print(f"File: {path}")
    print(f"Window UTC: [{out['window_utc']['start']}, {out['window_utc']['end']})")
    print(f"Opens: {out['opens']} | Closes: {out['closes']}")
    print(f"Realized PnL (sum close pnl): {out['realized_pnl_usdt']} USDT")
    print(f"Fees (on window rows):        {out['fees_usdt']} USDT")
    print(f"Net (pnl + fees):             {out['net_pnl_plus_fees_usdt']} USDT")
    wr = out["close_win_rate"]
    print(
        f"Close win rate: {wr if wr is not None else 'n/a'} "
        f"(wins={out['closes_wins']} losses={out['closes_losses']})"
    )
    print(f"Profit factor: {out['profit_factor']}")
    print("\nTop open reasons:")
    for k, v in out["open_reason_top"]:
        print(f"  {v:5d}  {k}")
    print("\nTop close reasons:")
    for k, v in out["close_reason_top"]:
        print(f"  {v:5d}  {k}")
    print("\nWorst symbols (by realized pnl on closes):")
    for row in out["by_symbol_closes_sorted_worst_pnl"]:
        print(
            f"  {row['symbol']:18} pnl={row['pnl']:+.4f} fee={row['fee']:.4f} "
            f"closes={row['closes']} opens={row['opens']}"
        )


if __name__ == "__main__":
    main()
