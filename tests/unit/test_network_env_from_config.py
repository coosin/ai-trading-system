"""network_env_from_config：Docker 环回代理改写与回退 URL（配对/回归）。"""
from __future__ import annotations

import os
from unittest.mock import patch

from src.modules.core.network_env_from_config import (
    build_proxy_url_from_config,
    docker_loopback_proxy_use_gateway_host,
    proxy_url_for_data_sources,
)
from src.modules.core.proxy_manager import ProxyManager


def _env_without_proxy_rewrite_flags() -> dict[str, str]:
    e = dict(os.environ)
    e.pop("OPENCLAW_DOCKER_NETWORK_HOST", None)
    e.pop("OPENCLAW_PROXY_LOOPBACK_REWRITE", None)
    return e


class TestDockerLoopbackProxyUseGatewayHost:
    def test_host_network_flag_disables_rewrite(self):
        with patch.dict(
            os.environ,
            {"OPENCLAW_DOCKER_NETWORK_HOST": "1"},
            clear=False,
        ):
            assert docker_loopback_proxy_use_gateway_host() is False

    def test_explicit_loopback_rewrite_off(self):
        with patch.dict(
            os.environ,
            {"OPENCLAW_PROXY_LOOPBACK_REWRITE": "0"},
            clear=False,
        ):
            assert docker_loopback_proxy_use_gateway_host() is False

    @patch("src.modules.core.network_env_from_config.os.path.exists")
    def test_dockerenv_true_implies_rewrite(self, mock_exists):
        mock_exists.return_value = True
        with patch.dict(os.environ, _env_without_proxy_rewrite_flags(), clear=True):
            assert docker_loopback_proxy_use_gateway_host() is True

    @patch("src.modules.core.network_env_from_config.os.path.exists")
    def test_no_dockerenv_implies_no_rewrite(self, mock_exists):
        mock_exists.return_value = False
        with patch.dict(os.environ, _env_without_proxy_rewrite_flags(), clear=True):
            assert docker_loopback_proxy_use_gateway_host() is False


class TestProxyUrlForDataSources:
    def test_prefers_http_proxy_env(self):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://192.168.1.2:7890"}, clear=False):
            assert proxy_url_for_data_sources(None) == "http://192.168.1.2:7890"

    def test_empty_when_no_env_and_no_config(self):
        base = _env_without_proxy_rewrite_flags()
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            base.pop(k, None)
        with patch.dict(os.environ, base, clear=True):
            assert proxy_url_for_data_sources(None) == ""


class TestBuildProxyUrlFromConfig:
    def test_builds_when_enabled(self):
        px = {
            "enabled": True,
            "global_proxy": {
                "enabled": True,
                "proxy_type": "http",
                "host": "127.0.0.1",
                "port": 7890,
            },
        }
        u = build_proxy_url_from_config(px)
        assert u == "http://127.0.0.1:7890"


class TestProxyManagerNormalizeLoopbackHost:
    @patch("src.modules.core.proxy_manager.docker_loopback_proxy_use_gateway_host", return_value=True)
    def test_rewrites_to_docker_gateway(self, _mock):
        pm = ProxyManager()
        assert pm._normalize_proxy_host_for_runtime("127.0.0.1") == "host.docker.internal"
        assert pm._normalize_proxy_host_for_runtime("localhost") == "host.docker.internal"

    @patch("src.modules.core.proxy_manager.docker_loopback_proxy_use_gateway_host", return_value=False)
    def test_keeps_loopback_for_host_network(self, _mock):
        pm = ProxyManager()
        assert pm._normalize_proxy_host_for_runtime("127.0.0.1") == "127.0.0.1"
        assert pm._normalize_proxy_host_for_runtime("10.0.0.1") == "10.0.0.1"
