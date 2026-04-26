"""
Binance Futures public endpoints (no API key) for redundancy.

This is used as a fallback when the primary exchange adapter cannot provide
funding rate / open interest quickly or reliably.

Endpoints (public, no signature):
  - Funding Rate (current): GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT
      field: lastFundingRate (string)
  - Open Interest (current): GET https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT
      field: openInterest (string)

Notes:
  - These are NOT exchange-account specific.
  - Mapping OKX symbol "BTC/USDT" -> Binance "BTCUSDT".
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


def _normalize_binance_symbol(symbol: str) -> str:
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


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


class BinancePublicProvider:
    def __init__(self, *, proxy_url: Optional[str] = None) -> None:
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
        min_iv = max(0.0, _env_float("OPENCLAW_BINANCE_PUBLIC_MIN_INTERVAL_SEC", 0.25))
        if min_iv <= 0:
            return
        now = time.monotonic()
        if self._last_request_mono > 0:
            gap = now - self._last_request_mono
            if gap < min_iv:
                await asyncio.sleep(min_iv - gap)

    async def _get_json(self, url: str, *, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        t0 = time.time()
        timeout = max(2.5, _env_float("OPENCLAW_BINANCE_PUBLIC_TIMEOUT_SEC", 6.5))
        proxy = await self._get_proxy()
        sess = await self._session_get()
        headers = {"accept": "application/json"}

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
                        return None, {"status": resp.status, "latency_ms": latency_ms}
                    try:
                        data = await resp.json()
                    except Exception:
                        return None, {"status": resp.status, "latency_ms": latency_ms, "error": "json_decode"}
                    return data if isinstance(data, dict) else {"raw": data}, {"status": resp.status, "latency_ms": latency_ms}
            except asyncio.TimeoutError:
                return None, {"status": "timeout", "latency_ms": int((time.time() - t0) * 1000)}
            except Exception as e:
                return None, {"status": "error", "latency_ms": int((time.time() - t0) * 1000), "error": type(e).__name__}

    async def get_funding_rate_current(self, symbol: str) -> Tuple[Optional[float], Dict[str, Any]]:
        sym = _normalize_binance_symbol(symbol)
        if not sym:
            return None, {"status": "empty_symbol"}
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        payload, meta = await self._get_json(url, params={"symbol": sym})
        if not isinstance(payload, dict):
            return None, meta
        fr = payload.get("lastFundingRate")
        try:
            return float(fr) if fr is not None else None, meta
        except Exception:
            meta["error"] = "invalid_funding_rate"
            return None, meta

    async def get_open_interest_current(self, symbol: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        sym = _normalize_binance_symbol(symbol)
        if not sym:
            return None, {"status": "empty_symbol"}
        url = "https://fapi.binance.com/fapi/v1/openInterest"
        payload, meta = await self._get_json(url, params={"symbol": sym})
        if not isinstance(payload, dict):
            return None, meta
        # { "openInterest": "12345.6", "symbol": "BTCUSDT", "time": 169..." }
        try:
            oi = payload.get("openInterest")
            out = {
                "symbol": symbol,
                "binance_symbol": payload.get("symbol") or sym,
                "openInterest": float(oi) if oi is not None else None,
                "time": payload.get("time"),
                "source": "binance_public",
            }
            return out, meta
        except Exception:
            meta["error"] = "invalid_open_interest"
            return None, meta


_GLOBAL: Optional[BinancePublicProvider] = None


async def get_binance_public_provider() -> BinancePublicProvider:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = BinancePublicProvider()
    return _GLOBAL

