"""route_catalog / surface 合并清单自检。"""
from __future__ import annotations

from src.modules.api import module_surface
from src.modules.api.route_catalog import extended_core_routes, read_pipeline_spec


def test_read_pipeline_starts_with_health():
    spec = read_pipeline_spec()
    steps = spec.get("steps") or []
    assert steps, "read_pipeline must have steps"
    first = steps[0]
    assert first.get("path") == "/api/v1/system/health"


def test_extended_routes_include_trades_analytics():
    paths = {r["path"] for r in extended_core_routes()}
    assert "/api/v1/trades/analytics/summary" in paths
    assert "/api/v1/data-hub/unified-snapshot" in paths


def test_build_static_route_catalog_merges_without_duplicate_paths():
    rows = module_surface.build_static_route_catalog()
    keys = [(r["method"], r["path"]) for r in rows]
    assert len(keys) == len(set(keys)), f"duplicate route entries: {len(keys)} vs {len(set(keys))}"
