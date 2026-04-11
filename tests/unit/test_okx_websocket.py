"""OKX WebSocket 辅助逻辑单测（无网络）。"""
from unittest.mock import MagicMock

import pytest

from src.modules.exchanges.okx_websocket import OKXWebSocketHub


@pytest.fixture
def mock_exchange():
    ex = MagicMock()
    ex.testnet = False
    ex.api_key = "test_key"
    ex.api_secret = "test_secret"
    ex.api_passphrase = "pp"
    ex._session = None
    ex._proxy_url = None
    ex._proxy_only = False
    ex.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
    return ex


def test_build_login_arg_shape(mock_exchange):
    hub = OKXWebSocketHub(mock_exchange)
    arg = hub.build_login_arg()
    assert set(arg.keys()) == {"apiKey", "passphrase", "timestamp", "sign"}
    assert arg["apiKey"] == "test_key"
    assert arg["passphrase"] == "pp"
    assert str(arg["timestamp"]).isdigit()
    assert isinstance(arg["sign"], str) and len(arg["sign"]) > 8


def test_get_cached_ticker_miss(mock_exchange):
    hub = OKXWebSocketHub(mock_exchange)
    assert hub.get_cached_ticker("BTC-USDT-SWAP", max_age_ms=1000) is None
