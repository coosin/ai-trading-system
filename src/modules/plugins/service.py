from __future__ import annotations

from typing import Any, Dict, List


def _is_parameter_required_result(skill: Dict[str, Any]) -> bool:
    result = skill.get("last_result") if isinstance(skill.get("last_result"), dict) else {}
    message = str(result.get("message") or skill.get("status") or "")
    errors = " ".join(str(x) for x in (result.get("errors") or []))
    text = f"{message} {errors}".lower()
    markers = ("缺少编辑请求", "缺少开发请求", "缺少审查请求", "未提供", "missing request", "request required")
    return any(marker.lower() in text for marker in markers)


def _normalize_skill_info(skill: Dict[str, Any]) -> Dict[str, Any]:
    """Separate callable readiness from last invocation result.

    Some parameterized skills legitimately fail when invoked without a request.
    Reporting that as the skill's operational status is misleading for MCP/CLI
    discovery, so expose both fields explicitly.
    """
    out = dict(skill)
    last_status = str(out.get("status") or "unknown")
    parameter_required = _is_parameter_required_result(out)
    enabled = bool(out.get("enabled", True))
    if not enabled:
        readiness = "disabled"
    elif parameter_required:
        readiness = "ready_requires_input"
    elif last_status == "failed":
        readiness = "attention"
    else:
        readiness = "ready"
    out["last_invocation_status"] = last_status
    out["operational_status"] = readiness
    out["parameter_required"] = parameter_required
    return out


class PluginsDomainService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def registry(self) -> Dict[str, Any]:
        plugin_manager = getattr(self.mc, "plugin_manager", None) if self.mc else None
        skill_manager = getattr(self.mc, "skill_manager", None) if self.mc else None
        plugins: Any = []
        skills: List[Dict[str, Any]] = []
        if plugin_manager:
            if hasattr(plugin_manager, "get_all_plugin_info"):
                plugins = plugin_manager.get_all_plugin_info()
            elif hasattr(plugin_manager, "plugins"):
                plugins = list(getattr(plugin_manager, "plugins", {}).keys())
        if skill_manager:
            if hasattr(skill_manager, "get_all_skills_info"):
                skills = skill_manager.get_all_skills_info()
            elif hasattr(skill_manager, "skills"):
                skills = [{"name": name} for name in sorted(getattr(skill_manager, "skills", {}).keys())]
        skills = [_normalize_skill_info(s) for s in skills if isinstance(s, dict)]
        return {
            "plugins": plugins,
            "skills": skills,
            "summary": {
                "plugin_count": len(plugins) if isinstance(plugins, (list, dict)) else 0,
                "skill_count": len(skills),
                "ready_skills": sum(1 for s in skills if str(s.get("operational_status")).startswith("ready")),
                "attention_skills": [s.get("name") for s in skills if s.get("operational_status") == "attention"],
            },
            "extension_points": [
                {
                    "name": "runtime_introspection",
                    "status": "loaded" if self._plugin_present(plugins, "runtime_introspection") else "available",
                    "description": "Expose runtime/API/MCP diagnostics without trading writes.",
                },
                {
                    "name": "data_provider",
                    "status": "available",
                    "description": "Add external market/on-chain/sentiment providers through PluginManager.",
                },
                {
                    "name": "post_trade_reviewer",
                    "status": "available",
                    "description": "Convert closed trades into review cards and lessons.",
                },
            ],
            "permissions": {
                "read": True,
                "suggestion": True,
                "low_risk_write": "requires_api_auth",
                "exchange_write": "forbidden_outside_execution_gateway",
            },
        }

    def _plugin_present(self, plugins: Any, name: str) -> bool:
        if isinstance(plugins, dict):
            return name in plugins or any(str((v or {}).get("name") or "") == name for v in plugins.values() if isinstance(v, dict))
        if isinstance(plugins, list):
            return any(str((p or {}).get("name") if isinstance(p, dict) else p) == name for p in plugins)
        return False
