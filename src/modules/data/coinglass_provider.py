"""
CoinGlass (Coinglass) Open API v4 provider.

We prefer the official API instead of scraping coinglass.com pages.
Docs: https://docs.coinglass.com/ (base URL https://open-api-v4.coinglass.com)

Env:
  - COINGLASS_API_KEY: required
  - COINGLASS_EXCHANGE: optional, default "OKX" (examples: "Binance", "OKX", "Bybit", ...)
  - COINGLASS_INTERVAL: optional, default "1h" (e.g. "1h", "4h", "1d")
  - COINGLASS_TIMEOUT_SEC: optional, default 12
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


_BASE_URL = "https://open-api-v4.coinglass.com"


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return str(v).strip() if v is not None and str(v).strip() else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def _normalize_symbol(symbol: str) -> str:
    """
    Convert common symbols to CoinGlass style pair symbol.
    - "BTC/USDT" -> "BTCUSDT"
    - "BTC-USDT" -> "BTCUSDT"
    - "BTCUSDT" -> "BTCUSDT"
    """
    s = str(symbol or "").strip().upper()
    if not s:
        return ""
    s = s.replace("-SWAP", "")
    if "/" in s:
        base, quote = s.split("/", 1)
        return f"{base.strip()}{quote.strip()}"
    if "-" in s:
        parts = [p for p in s.split("-") if p]
        if len(parts) >= 2:
            return f"{parts[0]}{parts[1]}"
    return s.replace("/", "").replace("-", "")


def _pick_latest_ohlc(rows: Any) -> Optional[Dict[str, Any]]:
    """
    CoinGlass v4 endpoints frequently return {"data": [...]} where each item contains
    timestamp + o/h/l/c fields (or similar). We keep it permissive and return the last item.
    """
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("result") or rows.get("list") or rows.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    item = rows[-1]
    return item if isinstance(item, dict) else None


class CoinGlassProvider:
    def __init__(self, api_key: str, *, proxy_url: Optional[str] = None) -> None:
        self.api_key = str(api_key or "").strip()
        self._proxy_url = proxy_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._last_request_mono = 0.0

    async def _get_proxy(self) -> Optional[str]:
        if self._proxy_url is not None:
            return self._proxy_url
        try:
            from src.utils.proxy_utils import get_proxy_url

            self._proxy_url = await get_proxy_url()
            return self._proxy_url
        except Exception:
            return None

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

    async def _throttle(self) -> None:
        min_iv = max(0.0, _env_float("OPENCLAW_COINGLASS_MIN_INTERVAL_SEC", 0.45))
        if min_iv <= 0:
            return
        now = time.monotonic()
        if self._last_request_mono > 0:
            gap = now - self._last_request_mono
            if gap < min_iv:
                await asyncio.sleep(min_iv - gap)

    async def _get_json(self, path: str, *, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Returns (payload, meta)
        meta: {status, latency_ms, error?}
        """
        t0 = time.time()
        url = f"{_BASE_URL}{path}"
        timeout = max(3.0, _env_float("COINGLASS_TIMEOUT_SEC", 12.0))
        proxy = await self._get_proxy()
        sess = await self._session_get()
        headers = {"accept": "application/json", "CG-API-KEY": self.api_key}

        async with self._lock:
            await self._throttle()
            self._last_request_mono = time.monotonic()
            try:
                async with sess.get(
                    url,
                    headers=headers,
                    params=params,
                    proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    latency_ms = int((time.time() - t0) * 1000)
                    if resp.status != 200:
                        return None, {"status": resp.status, "latency_ms": latency_ms, "error": "http_non_200"}
                    try:
                        data = await resp.json()
                    except Exception:
                        return None, {"status": resp.status, "latency_ms": latency_ms, "error": "json_decode"}
                    return data if isinstance(data, dict) else {"raw": data}, {"status": resp.status, "latency_ms": latency_ms}
            except asyncio.TimeoutError:
                return None, {"status": "timeout", "latency_ms": int((time.time() - t0) * 1000)}
            except Exception as e:
                return None, {"status": "error", "latency_ms": int((time.time() - t0) * 1000), "error": type(e).__name__}

    async def fetch_derivatives_snapshot(self, symbol: str) -> Dict[str, Any]:
        """
        Best-effort pull of OI / funding / liquidation for the given pair.
        """
        if not self.api_key:
            return {"enabled": False, "error": "missing_api_key"}

        exch = _env("COINGLASS_EXCHANGE", "OKX")
        interval = _env("COINGLASS_INTERVAL", "1h")
        pair = _normalize_symbol(symbol)
        if not pair:
            return {"enabled": True, "error": "empty_symbol"}

        # NOTE: Some endpoints accept limit; docs vary by endpoint/version.
        # We keep params minimal for compatibility.
        common = {"exchange": exch, "symbol": pair, "interval": interval}

        oi_raw, oi_meta = await self._get_json("/api/futures/open-interest/history", params=dict(common))
        fr_raw, fr_meta = await self._get_json("/api/futures/funding-rate/history", params=dict(common))
        liq_raw, liq_meta = await self._get_json("/api/futures/liquidation/history", params=dict(common))

        oi_last = _pick_latest_ohlc(oi_raw)
        fr_last = _pick_latest_ohlc(fr_raw)
        liq_last = _pick_latest_ohlc(liq_raw)

        return {
            "enabled": True,
            "provider": "coinglass_open_api_v4",
            "exchange": exch,
            "symbol": pair,
            "interval": interval,
            "open_interest": {"latest": oi_last, "meta": oi_meta},
            "funding_rate": {"latest": fr_last, "meta": fr_meta},
            "liquidation": {"latest": liq_last, "meta": liq_meta},
        }


_GLOBAL_PROVIDER: Optional[CoinGlassProvider] = None


async def get_coinglass_provider() -> Optional[CoinGlassProvider]:
    global _GLOBAL_PROVIDER
    if _GLOBAL_PROVIDER is not None:
        return _GLOBAL_PROVIDER
    api_key = _env("COINGLASS_API_KEY", "")
    if not api_key:
        return None
    _GLOBAL_PROVIDER = CoinGlassProvider(api_key=api_key)
    return _GLOBAL_PROVIDER


async def fetch_coinglass_snapshot(symbol: str) -> Dict[str, Any]:
    prov = await get_coinglass_provider()
    if not prov:
        return {"enabled": False, "error": "COINGLASS_API_KEY_not_set"}
    try:
        return await prov.fetch_derivatives_snapshot(symbol)
    except Exception as e:
        logger.debug("CoinGlass snapshot failed: %s", e)
        return {"enabled": True, "error": type(e).__name__}

