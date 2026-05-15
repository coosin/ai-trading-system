from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from src.modules.core.plugin_system import Plugin


class RuntimeIntrospectionPlugin(Plugin):
    """Read-only runtime capability marker for API/MCP integrations."""

    def __init__(self, config: Dict[str, Any]):
        merged = {
            "name": "runtime_introspection",
            "version": "1.0.0",
            "description": "Read-only runtime/API/MCP diagnostics plugin.",
            "enabled": True,
        }
        merged.update(config or {})
        super().__init__(merged)
        self.started = False
        self.loaded_at = datetime.now().isoformat()

    async def initialize(self) -> bool:
        return True

    async def start(self) -> bool:
        self.started = True
        return True

    async def stop(self) -> bool:
        self.started = False
        return True

    async def cleanup(self) -> bool:
        return True

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update(
            {
                "type": "observability",
                "safety": "read_only",
                "started": self.started,
                "loaded_at": self.loaded_at,
                "capabilities": [
                    "surface_registry_diagnostics",
                    "mcp_manifest_discovery",
                    "post_trade_review_visibility",
                ],
            }
        )
        return info
