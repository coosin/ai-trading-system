"""
AiCoin Open API provider (signed requests).

Docs:
  - Signature: https://docs.aicoin.com/apis/generate-signature
  - Markets:   https://docs.aicoin.com/apis/markets

Env:
  - AICOIN_ACCESS_KEY_ID: required
  - AICOIN_ACCESS_SECRET: required
  - AICOIN_TIMEOUT_SEC: optional, default 10
  - AICOIN_SYMBOL_COIN_TYPE_MAP: optional JSON mapping, e.g. {"BTC/USDT":"bitcoin","ETH/USDT":"ethereum"}

Notes:
  - All endpoints require AccessKeyId/SignatureNonce/Timestamp/Signature.
  - Signature algorithm per docs:
      str = "AccessKeyId=...&SignatureNonce=...&Timestamp=..."
      HMAC-SHA1(str, access_secret) -> hex string -> Base64(hex_bytes)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


_BASE_URL = "https://open.aicoin.com"


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return str(v).strip() if v is not None and str(v).strip() else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def _is_proxy_error(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            aiohttp.ClientProxyConnectionError,
            aiohttp.ClientHttpProxyError,
        ),
    )


def _coin_type_from_symbol(symbol: str) -> str:
    # Best-effort mapping to AiCoin coinType style.
    custom_raw = _env("AICOIN_SYMBOL_COIN_TYPE_MAP", "")
    if custom_raw:
        try:
            mapping = json.loads(custom_raw)
            if isinstance(mapping, dict):
                v = mapping.get(symbol) or mapping.get(str(symbol).upper())
                if isinstance(v, str) and v.strip():
                    return v.strip()
        except Exception:
            pass
    s = str(symbol or "").strip().upper()
    if not s:
        return "bitcoin"
    if "/" in s:
        base = s.split("/", 1)[0]
    elif "-" in s:
        base = s.split("-", 1)[0]
    else:
        base = s.replace("USDT", "").replace("USD", "")
    base = base.strip().upper()
    mapping = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binance-coin",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
    }
    return mapping.get(base, base.lower())


def _aicoin_signature(access_key_id: str, access_secret: str, signature_nonce: str, ts_sec: int) -> str:
    plain = f"AccessKeyId={access_key_id}&SignatureNonce={signature_nonce}&Timestamp={ts_sec}"
    digest = hmac.new(access_secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha1).hexdigest()
    # docs示例是对 hex 字符串做 base64
    return base64.b64encode(digest.encode("utf-8")).decode("utf-8")


class AiCoinProvider:
    def __init__(self, access_key_id: str, access_secret: str, *, proxy_url: Optional[str] = None) -> None:
        self.access_key_id = str(access_key_id or "").strip()
        self.access_secret = str(access_secret or "").strip()
        self._proxy_url = proxy_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._last_request_mono = 0.0
        # auth-denied circuit breaker: when backend returns "需要授权"/304,
        # skip hot-loop retries for a cooldown window.
        self._auth_denied_until_ts: float = 0.0
        self._last_auth_denied_reason: Optional[str] = None

    async def _get_proxy(self) -> Optional[str]:
        if _env("OPENCLAW_AICOIN_DISABLE_PROXY", "0").lower() in ("1", "true", "yes", "on"):
            self._proxy_url = None
            return None
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
        min_iv = max(0.0, _env_float("OPENCLAW_AICOIN_MIN_INTERVAL_SEC", 0.35))
        if min_iv <= 0:
            return
        now = time.monotonic()
        if self._last_request_mono > 0:
            gap = now - self._last_request_mono
            if gap < min_iv:
                await asyncio.sleep(min_iv - gap)

    def _auth_params(self) -> Dict[str, Any]:
        ts = int(time.time())
        nonce = secrets.token_hex(4)
        sig = _aicoin_signature(self.access_key_id, self.access_secret, nonce, ts)
        return {
            "AccessKeyId": self.access_key_id,
            "SignatureNonce": nonce,
            "Timestamp": str(ts),
            "Signature": sig,
        }

    async def _get_json(self, path: str, *, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        t0 = time.time()
        timeout = max(3.0, _env_float("AICOIN_TIMEOUT_SEC", 10.0))
        proxy = await self._get_proxy()
        sess = await self._session_get()
        query = dict(params or {})
        query.update(self._auth_params())
        url = f"{_BASE_URL}{path}"

        async with self._lock:
            await self._throttle()
            self._last_request_mono = time.monotonic()
            try:
                async def _do_req(proxy_url: Optional[str]):
                    async with sess.get(
                        url,
                        params=query,
                        proxy=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as resp:
                        latency_ms = int((time.time() - t0) * 1000)
                        try:
                            data = await resp.json()
                        except Exception:
                            return None, {"status": resp.status, "latency_ms": latency_ms, "error": "json_decode"}
                        if resp.status != 200:
                            return (
                                data if isinstance(data, dict) else None,
                                {"status": resp.status, "latency_ms": latency_ms, "error": "http_non_200"},
                            )
                        return data if isinstance(data, dict) else {"raw": data}, {"status": resp.status, "latency_ms": latency_ms}

                try:
                    return await _do_req(proxy)
                except Exception as e:
                    # Proxy failed -> one direct retry for better resilience
                    if proxy and _is_proxy_error(e):
                        self._proxy_url = None
                        data, meta = await _do_req(None)
                        meta = dict(meta or {})
                        meta["proxy_fallback"] = "direct"
                        return data, meta
                    raise
            except asyncio.TimeoutError:
                return None, {"status": "timeout", "latency_ms": int((time.time() - t0) * 1000)}
            except Exception as e:
                return None, {"status": "error", "latency_ms": int((time.time() - t0) * 1000), "error": type(e).__name__}

    async def fetch_futures_interest(self) -> Dict[str, Any]:
        payload, meta = await self._get_json(
            "/api/v2/futures/interest",
            params={"lan": "en", "page": 1, "pageSize": 20, "currency": "usd"},
        )
        out: Dict[str, Any] = {"meta": meta}
        if not isinstance(payload, dict):
            out["error"] = "empty_payload"
            return out
        out["success"] = bool(payload.get("success"))
        out["errorCode"] = payload.get("errorCode")
        out["error"] = payload.get("error")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("list") if isinstance(data.get("list"), list) else []
        out["list"] = rows[:20]
        return out

    async def fetch_indicator_kline(self, symbol: str, indicator_key: str) -> Dict[str, Any]:
        coin_type = _coin_type_from_symbol(symbol)
        payload, meta = await self._get_json(
            "/api/v2/indicatorKline/getTradingPair",
            params={"coinType": coin_type, "indicator_key": indicator_key},
        )
        out: Dict[str, Any] = {"meta": meta, "coinType": coin_type, "indicator_key": indicator_key}
        if not isinstance(payload, dict):
            out["error"] = "empty_payload"
            return out
        out["success"] = bool(payload.get("success"))
        out["errorCode"] = payload.get("errorCode")
        out["error"] = payload.get("error")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        out["list"] = data.get("list") if isinstance(data.get("list"), list) else []
        return out

    async def fetch_market_snapshot(self, symbol: str) -> Dict[str, Any]:
        """
        Best-effort snapshot for DataSourceHub extra provider.
        """
        now = time.time()
        deny_cooldown = max(60.0, _env_float("OPENCLAW_AICOIN_AUTH_DENIED_COOLDOWN_SEC", 900.0))
        if self._auth_denied_until_ts > now:
            return {
                "enabled": True,
                "provider": "aicoin_open_api",
                "symbol": symbol,
                "auth_denied_cooldown": True,
                "auth_denied_until": int(self._auth_denied_until_ts),
                "auth_denied_reason": self._last_auth_denied_reason or "need_authorization",
            }

        # 1) broad futures interest rankings
        fut = await self.fetch_futures_interest()
        # 2) indicatorKline for funding-rate + liquidation related series
        fr = await self.fetch_indicator_kline(symbol, "fr")
        liq = await self.fetch_indicator_kline(symbol, "aili")
        tvol = await self.fetch_indicator_kline(symbol, "tvolume")

        # Keep payload bounded
        def _tail(rows: Any, n: int = 20) -> Any:
            if isinstance(rows, list):
                return rows[-n:]
            return []

        out = {
            "enabled": True,
            "provider": "aicoin_open_api",
            "symbol": symbol,
            "futures_interest": {
                "success": fut.get("success"),
                "errorCode": fut.get("errorCode"),
                "error": fut.get("error"),
                "meta": fut.get("meta"),
                "top": _tail(fut.get("list"), 20),
            },
            "funding_rate_series": {
                "success": fr.get("success"),
                "errorCode": fr.get("errorCode"),
                "error": fr.get("error"),
                "meta": fr.get("meta"),
                "rows": _tail(fr.get("list"), 30),
            },
            "liquidation_series": {
                "success": liq.get("success"),
                "errorCode": liq.get("errorCode"),
                "error": liq.get("error"),
                "meta": liq.get("meta"),
                "rows": _tail(liq.get("list"), 30),
            },
            "open_interest_volume_series": {
                "success": tvol.get("success"),
                "errorCode": tvol.get("errorCode"),
                "error": tvol.get("error"),
                "meta": tvol.get("meta"),
                "rows": _tail(tvol.get("list"), 30),
            },
        }
        # If backend explicitly says not authorized, enter cooldown to protect control-plane latency.
        err_codes = []
        for blk in (fut, fr, liq, tvol):
            try:
                if isinstance(blk, dict) and blk.get("errorCode") is not None:
                    err_codes.append(int(blk.get("errorCode")))
            except Exception:
                pass
        denied = any(code == 304 for code in err_codes)
        if denied:
            self._auth_denied_until_ts = time.time() + deny_cooldown
            self._last_auth_denied_reason = "errorCode=304 需要授权"
            out["auth_denied_cooldown"] = True
            out["auth_denied_until"] = int(self._auth_denied_until_ts)
            out["auth_denied_reason"] = self._last_auth_denied_reason
        return out


_GLOBAL_PROVIDER: Optional[AiCoinProvider] = None


async def get_aicoin_provider() -> Optional[AiCoinProvider]:
    global _GLOBAL_PROVIDER
    if _GLOBAL_PROVIDER is not None:
        return _GLOBAL_PROVIDER
    ak = _env("AICOIN_ACCESS_KEY_ID", "")
    sec = _env("AICOIN_ACCESS_SECRET", "")
    if not ak or not sec:
        return None
    _GLOBAL_PROVIDER = AiCoinProvider(access_key_id=ak, access_secret=sec)
    return _GLOBAL_PROVIDER


async def fetch_aicoin_snapshot(symbol: str) -> Dict[str, Any]:
    p = await get_aicoin_provider()
    if not p:
        return {"enabled": False, "error": "AICOIN_ACCESS_KEY_ID_or_AICOIN_ACCESS_SECRET_not_set"}
    try:
        return await p.fetch_market_snapshot(symbol)
    except Exception as e:
        logger.debug("AiCoin snapshot failed: %s", e)
        return {"enabled": True, "error": type(e).__name__}

