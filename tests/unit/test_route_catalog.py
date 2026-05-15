"""route_catalog / surface 合并清单自检。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.api import module_surface
from src.modules.api.standard_domains import STANDARD_DOMAINS
from src.modules.api.server import APIServer
from src.modules.api.route_catalog import extended_core_routes, read_pipeline_spec
from src.modules.api.standard_registry import canonical_routes


def test_read_pipeline_starts_with_health():
    spec = read_pipeline_spec()
    steps = spec.get("steps") or []
    assert steps, "read_pipeline must have steps"
    first = steps[0]
    assert first.get("path") == "/api/v1/system/health"


def test_extended_routes_include_standard_profit_loop():
    paths = {r["path"] for r in extended_core_routes()}
    assert "/api/v1/trades/lifecycle" in paths
    assert "/api/v1/data/snapshot" in paths
    assert "/api/v1/commander/system-mastery" in paths


def test_build_static_route_catalog_merges_without_duplicate_paths():
    rows = module_surface.build_static_route_catalog()
    keys = [(r["method"], r["path"]) for r in rows]
    assert len(keys) == len(set(keys)), f"duplicate route entries: {len(keys)} vs {len(set(keys))}"


def test_domain_registries_match_canonical_surface():
    from importlib import import_module

    canonical_by_domain = {domain: set() for domain in STANDARD_DOMAINS}
    for route in canonical_routes():
        if route.status == "canonical":
            canonical_by_domain.setdefault(route.domain, set()).add(route.capability)

    for domain in STANDARD_DOMAINS:
        registry = import_module(f"src.modules.{domain}.registry")
        assert getattr(registry, "DOMAIN") == domain
        assert set(getattr(registry, "CAPABILITIES")) == canonical_by_domain[domain]


@pytest.mark.asyncio
async def test_plugin_manager_uses_dedicated_plugin_root(tmp_path, monkeypatch):
    from src.modules.core.plugin_system import PluginManager

    monkeypatch.chdir(tmp_path)
    (tmp_path / "src/modules/plugins").mkdir(parents=True)
    (tmp_path / "src/modules/plugins/__pycache__").mkdir()
    (tmp_path / "plugins/__pycache__").mkdir(parents=True)

    manager = PluginManager()
    await manager.initialize()

    assert str(tmp_path / "src/modules/plugins") not in manager.plugin_paths
    assert str(tmp_path / "plugins") in manager.plugin_paths
    assert await manager.load_plugins() == []


@pytest.mark.asyncio
async def test_runtime_routes_have_no_duplicate_or_removed_legacy_paths():
    class _Controller:
        async def get_system_status(self):
            return {"system_status": "running", "module_statuses": {}, "execution_spine": {}}

        def get_exchange(self):
            return None

    APIServer._active_instance = None
    api = APIServer(config_manager=None, main_controller=_Controller(), host="127.0.0.1", port=8000)
    api.trusted_hosts = ["testserver", "127.0.0.1", "localhost"]
    api.app = FastAPI()
    await api._add_middleware()
    await api._setup_routes()

    keys = []
    paths = set()
    for route in api.app.routes:
        path = getattr(route, "path", "")
        methods = tuple(sorted(getattr(route, "methods", []) or []))
        if path.startswith("/api/v1"):
            keys.append((methods, path))
            paths.add(path)

    assert len(keys) == len(set(keys))
    assert not any("__legacy_removed" in path for path in paths)
    assert not any(path.startswith("/api/v1/strategies") for path in paths)

    response = TestClient(api.app).get("/api/v1/control-center/state")
    assert response.status_code == 200
    assert response.json().get("success") is True
