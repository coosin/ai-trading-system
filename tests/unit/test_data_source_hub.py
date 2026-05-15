import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.data.data_source_hub import DataSourceHub


@pytest.mark.asyncio
async def test_intel_channel_parallelizes_third_party_and_uses_news_cache(monkeypatch):
    mc = MagicMock()
    mc.config_manager = MagicMock()
    mc.config_manager.get_config_path_sync = MagicMock(return_value={})
    mc.get_ai_managed_config = AsyncMock(
        return_value={
            "intel_collectors": ["third_party.sentiment", "third_party.news"],
            "fetch_timeout_sec": 6.0,
            "fetch_retry_count": 1,
            "fetch_retry_backoff_sec": 0.0,
            "extra_providers": [],
        }
    )

    active = 0
    max_active = 0
    gate = asyncio.Event()
    started = 0

    async def _enter_and_wait():
        nonlocal active, max_active, started
        active += 1
        started += 1
        max_active = max(max_active, active)
        if started >= 2:
            gate.set()
        await gate.wait()
        await asyncio.sleep(0.01)
        active -= 1

    class _ThirdParty:
        async def get_comprehensive_sentiment(self, symbol: str):
            await _enter_and_wait()
            return {"symbol": symbol, "score": 0.61}

        async def get_news_sentiment(self, symbol: str):
            await _enter_and_wait()
            return {}

    mc.third_party_data_integrator = _ThirdParty()
    hub = DataSourceHub(mc)
    hub._cache_set("third_party_news:BTC/USDT", {"symbol": "BTC/USDT", "articles": 7, "average_sentiment": 0.55})

    out = await hub.get_intel_channel("BTC/USDT")

    assert max_active >= 2
    assert out["sentiment"]["score"] == 0.61
    assert out["news"]["articles"] == 7
    assert out["collector"]["health"]["third_party.news"]["status"] == "cache"
    assert out["health"]["third_party"] == "ok"


@pytest.mark.asyncio
async def test_fetch_safe_recreates_coroutine_for_retry():
    mc = MagicMock()
    mc.config_manager = MagicMock()
    mc.config_manager.get_config_path_sync = MagicMock(return_value={})
    mc.get_ai_managed_config = AsyncMock(
        return_value={
            "fetch_timeout_sec": 6.0,
            "fetch_retry_count": 2,
            "fetch_retry_backoff_sec": 0.0,
        }
    )
    hub = DataSourceHub(mc)

    calls = 0

    async def _job():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("first_fail")
        return {"ok": True}

    health = {}
    errors = []
    out = await hub._fetch_safe("retry.demo", lambda: _job(), default={}, health=health, errors=errors)

    assert out == {"ok": True}
    assert calls == 2
    assert health["retry.demo"]["status"] == "ok"
    assert health["retry.demo"]["attempt"] == 2
    assert errors == []
