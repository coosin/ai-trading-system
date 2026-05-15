from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from src.modules.exchanges.exchange_base import ExchangeInfo
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


def test_transport_reset_error_detects_payload_and_disconnect_markers():
    assert OKXExchange._is_transport_reset_error(aiohttp.ClientPayloadError("payload is not completed"))
    assert OKXExchange._is_transport_reset_error(ConnectionError("server disconnected"))
    assert not OKXExchange._is_transport_reset_error(ValueError("plain parse failure"))


@pytest.mark.asyncio
async def test_get_exchange_info_falls_back_to_cached_value_when_refresh_fails():
    ex = _exchange()
    cached_info = ExchangeInfo(
        exchange_id="okx",
        name="OKX",
        api_url=ex.api_url,
        ws_url=ex.ws_url,
        rate_limit=20,
        supported_symbols=["BTC/USDT/SWAP"],
        fee_structure={"maker": 0.001},
    )
    ex._exchange_info_cache = (1.0, cached_info)
    ex._exchange_info_ttl_s = 0.0
    ex._make_request = AsyncMock(side_effect=RuntimeError("network down"))

    out = await ex.get_exchange_info()

    assert out is cached_info


@pytest.mark.asyncio
async def test_get_swap_symbol_info_falls_back_to_cached_payload_when_refresh_fails():
    ex = _exchange()
    ex._instrument_cache_ttl_s = 0.0
    inst_id = ex._to_okx_inst_id("BTC/USDT", default_type="SWAP")
    cached_payload = {"instId": inst_id, "minSz": 1.0, "lotSz": 1.0, "tickSz": "0.1"}
    ex._instrument_cache[inst_id] = (1.0, cached_payload)
    ex._make_request = AsyncMock(side_effect=RuntimeError("network down"))

    out = await ex.get_swap_symbol_info("BTC/USDT")

    assert out == cached_payload


@pytest.mark.asyncio
async def test_make_request_rebuilds_session_on_client_payload_error():
    ex = _exchange()
    ex._session = MagicMock()
    ex._mark_request_failure = AsyncMock()
    ex._mark_request_success = AsyncMock()
    ex._record_payload_sample = AsyncMock()
    ex._rebuild_session = AsyncMock()
    ex._proxy_url = None

    responses = [aiohttp.ClientPayloadError("Response payload is not completed"), [{"instId": "BTC-USDT-SWAP"}]]

    class _Req:
        def __init__(self, item):
            self._item = item
            self.status = 200

        async def __aenter__(self):
            if isinstance(self._item, Exception):
                raise self._item
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {"code": "0", "data": self._item}

    class _Session:
        def get(self, *args, **kwargs):
            return _Req(responses.pop(0))

    ex._session = _Session()

    out = await ex._make_request("GET", "/api/v5/public/instruments", {"instType": "SWAP"})

    assert out == [{"instId": "BTC-USDT-SWAP"}]
    ex._rebuild_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_make_request_public_endpoint_does_not_require_auth_headers():
    ex = OKXExchange({"testnet": False})
    ex._mark_request_failure = AsyncMock()
    ex._mark_request_success = AsyncMock()
    ex._record_payload_sample = AsyncMock()
    ex._rebuild_session = AsyncMock()
    ex._proxy_url = None

    seen_headers = {}

    class _Req:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {"code": "0", "data": [{"ts": "1"}]}

    class _Session:
        def get(self, *args, **kwargs):
            seen_headers.update(kwargs.get("headers") or {})
            return _Req()

    ex._session = _Session()

    out = await ex._make_request("GET", "/api/v5/public/time")

    assert out == [{"ts": "1"}]
    assert "OK-ACCESS-KEY" not in seen_headers
    assert seen_headers["Content-Type"] == "application/json"
