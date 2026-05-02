import json
import time
import math
import urllib.request
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _parse_iso_ts(s: Any) -> Optional[float]:
    """
    Parse ISO8601 timestamps like:
      - 2026-04-29T08:57:54.358668Z
      - 2026-04-29T16:49:31.175947
    Return unix seconds (float) or None.
    """
    if not s:
        return None
    try:
        ss = str(s).strip()
        # Normalize Z suffix.
        if ss.endswith("Z"):
            ss = ss[:-1] + "+00:00"
        # If no timezone part exists, assume UTC.
        if "T" in ss and ("+" not in ss and "-" not in ss.split("T")[-1]):
            # Very permissive: try fromisoformat; if fails, fallback.
            dt = datetime.fromisoformat(ss)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        dt = datetime.fromisoformat(ss)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _infer_side(trace: Dict[str, Any]) -> Optional[str]:
    side = trace.get("side")
    if isinstance(side, str) and side.lower() in ("long", "short"):
        return side.lower()
    # Some traces use intent extras / reasoning to infer side.
    intent = trace.get("intent") or {}
    if isinstance(intent, dict):
        reasoning = str(intent.get("reasoning") or "")
        # Chinese hints used in existing scripts.
        if "做空" in reasoning or " short" in reasoning.lower():
            return "short"
        if "做多" in reasoning or " long" in reasoning.lower():
            return "long"
    reasoning = str(trace.get("reasoning") or "")
    if "做空" in reasoning or " short" in reasoning.lower():
        return "short"
    if "做多" in reasoning or " long" in reasoning.lower():
        return "long"
    return None


@dataclass(frozen=True)
class Kline:
    ts: float  # unix seconds
    o: float
    h: float
    l: float
    c: float


def _fetch_json(url: str, timeout_s: float = 20.0) -> Any:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def fetch_klines(
    api_base: str,
    symbol: str,
    timeframe: str = "5m",
    limit: int = 240,
    timeout_s: float = 20.0,
) -> List[Kline]:
    """
    Fetch klines from local trading system API.
    Assumes endpoint:
      /api/v1/market/klines?symbol=...&timeframe=...&limit=...
    Returns sorted klines by ts.
    """
    q = urllib.parse.urlencode(
        {"symbol": symbol, "timeframe": timeframe, "limit": str(limit)}
    )
    url = api_base.rstrip("/") + "/api/v1/market/klines?" + q
    data = _fetch_json(url, timeout_s=timeout_s)

    rows = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        # best-effort: common shapes
        rows = data.get("data") or data.get("result") or data.get("rows")
        if rows is None:
            # sometimes dict has numeric keys
            for k in ("klines", "candles"):
                if k in data and isinstance(data[k], list):
                    rows = data[k]
                    break
    if not isinstance(rows, list):
        return []

    out: List[Kline] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            # timestamp can be ms or seconds; we detect by magnitude.
            ts_raw = float(row.get("timestamp") or 0)
            if ts_raw <= 0:
                continue
            ts = ts_raw / 1000.0 if ts_raw > 1e12 else ts_raw
            o = float(row.get("open"))
            h = float(row.get("high"))
            l = float(row.get("low"))
            c = float(row.get("close"))
            out.append(Kline(ts=ts, o=o, h=h, l=l, c=c))
        except Exception:
            continue
    out.sort(key=lambda x: x.ts)
    return out


def _nearest_index_by_ts(candles: List[Kline], t: float) -> Optional[int]:
    """
    Return last index i where candles[i].ts <= t, or None.
    """
    idx = None
    for i, k in enumerate(candles):
        if k.ts <= t:
            idx = i
        else:
            break
    return idx


def slice_candles(candles: List[Kline], t1: float, t2: float) -> List[Kline]:
    """
    Inclusive slice where ts in [t1, t2].
    """
    out: List[Kline] = []
    for k in candles:
        if k.ts < t1:
            continue
        if k.ts > t2:
            break
        out.append(k)
    return out


def quality_metrics(
    candles: List[Kline],
    t_entry: float,
    side: str,
    horizon_sec: float,
    now_ts: Optional[float] = None,
) -> Optional[Dict[str, float]]:
    """
    Compute realized metrics within available time:
      - entry at nearest candle close at/before t_entry
      - exit at nearest candle close at/before min(t_entry+horizon, now_ts)
      - MFE/MAE computed within the slice.
    Returns None if insufficient candles.
    """
    if not candles or len(candles) < 3:
        return None

    entry_idx = _nearest_index_by_ts(candles, t_entry)
    if entry_idx is None:
        return None
    entry = candles[entry_idx].c
    if entry <= 0:
        return None

    effective_end = t_entry + horizon_sec
    if now_ts is not None:
        effective_end = min(effective_end, now_ts)

    end_idx = _nearest_index_by_ts(candles, effective_end)
    if end_idx is None or end_idx <= entry_idx:
        return None

    seg = candles[entry_idx : end_idx + 1]
    if not seg:
        return None

    close_end = seg[-1].c
    if side == "long":
        ret = (close_end - entry) / entry
        mfe = (max(x.h for x in seg) - entry) / entry
        mae = (min(x.l for x in seg) - entry) / entry
    else:
        ret = (entry - close_end) / entry
        mfe = (entry - min(x.l for x in seg)) / entry
        mae = (entry - max(x.h for x in seg)) * (-1.0) / entry  # negative

    # Composite score: reward ret & mfe, penalize adverse mae magnitude.
    # Keep consistent with existing scripts (ret + 0.6*mfe + 0.4*mae).
    score = ret + 0.6 * mfe + 0.4 * mae
    return {
        "ret_h": ret,
        "mfe_h": mfe,
        "mae_h": mae,
        "score_h": score,
        "close_end": close_end,
        "n_candles": float(len(seg)),
    }


def evaluate_traces_quality(
    traces: List[Dict[str, Any]],
    *,
    api_base: str,
    horizon_sec: float,
    timeframe: str = "5m",
    kline_limit: int = 240,
    now_ts: Optional[float] = None,
    max_traces: int = 30,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Evaluate realized quality for up to max_traces.
    Returns (rows, summary).
    """
    if now_ts is None:
        now_ts = time.time()

    # Cache by symbol.
    kline_cache: Dict[str, List[Kline]] = {}

    out_rows: List[Dict[str, Any]] = []
    for t in traces[:max_traces]:
        if not isinstance(t, dict):
            continue
        symbol = t.get("symbol")
        if not symbol or not isinstance(symbol, str) or "/" not in symbol:
            continue
        created_at = _parse_iso_ts(t.get("created_at") or t.get("updated_at"))
        if created_at is None:
            continue
        side = _infer_side(t)
        if side not in ("long", "short"):
            continue
        if symbol not in kline_cache:
            kline_cache[symbol] = fetch_klines(
                api_base=api_base,
                symbol=symbol,
                timeframe=timeframe,
                limit=kline_limit,
            )
        m = quality_metrics(
            kline_cache[symbol],
            t_entry=created_at,
            side=side,
            horizon_sec=horizon_sec,
            now_ts=now_ts,
        )
        if not m:
            continue
        out_rows.append(
            {
                "trace_id": t.get("trace_id"),
                "symbol": symbol,
                "side": side,
                "created_at": t.get("created_at"),
                "guard_reason": ((t.get("guard") or {}) or {}).get("reason"),
                "action": t.get("action") or ((t.get("execution") or {}) or {}).get("action"),
                **m,
            }
        )

    summary: Dict[str, Any] = {
        "n": len(out_rows),
        "avg_ret_h": float(sum(r["ret_h"] for r in out_rows) / len(out_rows)) if out_rows else None,
        "avg_mfe_h": float(sum(r["mfe_h"] for r in out_rows) / len(out_rows)) if out_rows else None,
        "avg_mae_h": float(sum(r["mae_h"] for r in out_rows) / len(out_rows)) if out_rows else None,
        "avg_score_h": float(sum(r["score_h"] for r in out_rows) / len(out_rows)) if out_rows else None,
        "hit_rate_ret_positive": (
            float(sum(1 for r in out_rows if r["ret_h"] and r["ret_h"] > 0) / len(out_rows))
            if out_rows
            else None
        ),
    }
    return out_rows, summary

