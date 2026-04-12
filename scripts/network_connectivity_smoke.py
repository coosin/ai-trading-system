#!/usr/bin/env python3
"""
对外部行情与 LLM 网关做只读烟测（不下单）。
用法：在项目根目录  python scripts/network_connectivity_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 与主程序一致：从仓库根目录加载 .env（否则终端直接跑脚本时 os.environ 里没有密钥）
try:
    from dotenv import load_dotenv

    _env = ROOT / ".env"
    if _env.is_file():
        load_dotenv(_env)
    _local = ROOT / ".env.local"
    if _local.is_file():
        load_dotenv(_local, override=True)
except ImportError:
    pass


async def _httpx_get(
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
) -> tuple[int, str]:
    import httpx

    proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or None
    kw: dict = {"timeout": 20.0, "http2": False}
    if proxy:
        kw["proxy"] = proxy
        kw["trust_env"] = False
    async with httpx.AsyncClient(**kw) as client:
        r = await client.get(url, headers=headers or {}, params=params)
        return r.status_code, (r.text or "")[:300]


async def main() -> int:
    results: list[tuple[str, str]] = []

    try:
        code, body = await _httpx_get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT")
        ok = code == 200 and "last" in body
        results.append(("OKX ticker (public REST)", "OK" if ok else "HTTP %s %s" % (code, body[:80])))
    except Exception as e:
        results.append(("OKX ticker (public REST)", "ERR %s: %s" % (type(e).__name__, e)))

    try:
        code, body = await _httpx_get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT")
        ok = code == 200 and "lastPrice" in body
        results.append(("Binance 24h ticker", "OK" if ok else "HTTP %s" % code))
    except Exception as e:
        results.append(("Binance 24h ticker", "ERR %s: %s" % (type(e).__name__, e)))

    try:
        code, body = await _httpx_get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
        )
        ok = code == 200 and "bitcoin" in body
        results.append(("CoinGecko simple/price", "OK" if ok else "HTTP %s" % code))
    except Exception as e:
        results.append(("CoinGecko simple/price", "ERR %s: %s" % (type(e).__name__, e)))

    try:
        code, _ = await _httpx_get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": "Bearer sk-smoke-invalid"},
        )
        ok = code in (200, 401, 403)
        results.append(("OpenAI API reachability", "HTTP %s%s" % (code, " OK" if ok else " unexpected")))
    except Exception as e:
        results.append(("OpenAI API reachability", "ERR %s: %s" % (type(e).__name__, e)))

    key = (os.getenv("OKX_API_KEY") or "").strip()
    # 与 .env.example / OKXExchange 一致：主项目用 OKX_SECRET；部分文档写成 OKX_SECRET_KEY
    sec = (os.getenv("OKX_SECRET_KEY") or os.getenv("OKX_SECRET") or "").strip()
    passphrase = (os.getenv("OKX_PASSPHRASE") or "").strip()
    if key and sec and passphrase:
        try:
            from src.modules.exchanges.okx import OKXExchange

            cfg = {
                "api_key": key,
                "api_secret": sec,
                "passphrase": passphrase,
                "testnet": str(os.getenv("OKX_TESTNET", "")).strip().lower() in ("1", "true", "yes"),
            }
            ex = OKXExchange(cfg)
            await ex.initialize()
            bal = await ex.get_balance()
            await ex.cleanup()
            results.append(("OKX signed get_balance", "OK keys=%d" % len(bal)))
        except Exception as e:
            results.append(("OKX signed get_balance", "ERR %s: %s" % (type(e).__name__, e)))
    else:
        results.append(("OKX signed get_balance", "SKIP (no OKX_* in env)"))

    try:
        import importlib.util

        ellm_path = ROOT / "src/modules/core/enhanced_llm_manager.py"
        spec = importlib.util.spec_from_file_location("_oc_enhanced_llm_manager", ellm_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load enhanced_llm_manager")
        ellm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ellm)
        ModelConfig = ellm.ModelConfig
        ModelProvider = ellm.ModelProvider
        OpenAIProvider = ellm.OpenAIProvider

        mc = ModelConfig(
            provider=ModelProvider.OPENAI,
            model_id="gpt-4o-mini",
            display_name="smoke",
            api_key="sk-smoke",
            base_url="https://api.openai.com/v1",
            timeout=15.0,
            max_retries=1,
        )
        p = OpenAIProvider(mc)
        await p.initialize()
        assert p.session is not None
        r = await p.session.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": "Bearer sk-smoke"},
        )
        code = r.status_code
        await p.cleanup()
        ok = code in (401, 403)
        results.append(("OpenAIProvider httpx session", "HTTP %s%s" % (code, " OK" if ok else "")))
    except Exception as e:
        results.append(("OpenAIProvider httpx session", "ERR %s: %s" % (type(e).__name__, e)))

    for name, status in results:
        print("%s: %s" % (name, status))
    failed = [x for x in results if x[1].startswith("ERR") or ("unexpected" in x[1])]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
