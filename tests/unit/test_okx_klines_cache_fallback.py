import time
from unittest.mock import AsyncMock

import pytest

from src.modules.exchanges.okx import OKXExchange


def _exchange() -> OKXExchange:
    return OKXExchange(
        {
            "api_key": "k",
            "api_secret": "s",
            "api_passphrase": "p",
            "testnet": False,
        }
    )


@pytest.mark.asyncio
async def test_fetch_klines_cached_uses_stale_cache_on_refresh_failure():
    ex = _exchange()
    ex._klines_cache_ttl_s = 0.0
    ex._klines_stale_max_s = 300.0
    key = ex._klines_cache_key("BTC-USDT-SWAP", "1H", 100)
    cached_rows = [{"timestamp": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0, "quote_volume": 15.0}]
    ex._klines_cache[key] = (time.time() - 100.0, cached_rows)
    ex._make_request = AsyncMock(side_effect=RuntimeError("network down"))

    out = await ex._fetch_klines_cached("BTC-USDT-SWAP", "1H", 100)

    assert out == cached_rows


def test_payload_field_matrix_recognizes_candle_positional_fields():
    ex = _exchange()

    fields = ex._flatten_fields([["1", "2", "3", "4", "5", "6", "7", "8"]])
    missing = ex._missing_expected_fields("candles", fields)

    assert "0" in fields
    assert "0[5]" in fields
    assert missing == []
