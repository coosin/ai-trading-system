import os

from src.modules.core.network_env_from_config import (
    apply_proxy_environment_from_merged_config,
    build_proxy_url_from_config,
)


def test_build_proxy_url_basic():
    url = build_proxy_url_from_config(
        {
            "enabled": True,
            "global_proxy": {
                "enabled": True,
                "proxy_type": "http",
                "host": "127.0.0.1",
                "port": 7890,
            },
        }
    )
    assert url == "http://127.0.0.1:7890"


def test_build_proxy_disabled():
    assert build_proxy_url_from_config({"enabled": False}) is None


def test_merge_no_proxy(monkeypatch):
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.setenv("NO_PROXY", "redis,okx.com")
    root = {
        "proxy": {
            "enabled": True,
            "apply_to_process_env": True,
            "respect_existing_env": False,
            "force_override_env": True,
            "merge_no_proxy_from_config": True,
            "global_proxy": {
                "enabled": True,
                "proxy_type": "http",
                "host": "10.0.0.1",
                "port": 8888,
            },
            "bypass_domains": ["localhost"],
            "no_proxy_extra": [".internal"],
        }
    }
    apply_proxy_environment_from_merged_config(root)
    np = os.environ.get("NO_PROXY", "")
    assert "redis" in np
    assert "localhost" in np
    assert ".internal" in np
    assert os.environ.get("HTTP_PROXY", "").startswith("http://")
