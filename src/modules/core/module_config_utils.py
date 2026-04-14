"""
Utilities to normalize module config resolution.

Priority:
1) module defaults
2) ConfigManager section snapshot (if provided)
3) explicit constructor config
"""

from typing import Any, Dict, Optional


def deep_merge_dict(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for k, v in (updates or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = deep_merge_dict(merged[k], v)
        else:
            merged[k] = v
    return merged


def resolve_module_config(
    config: Optional[Dict[str, Any]],
    config_manager: Any,
    section: str,
    defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged = dict(defaults or {})
    if config_manager and hasattr(config_manager, "get_config_sync"):
        section_cfg = config_manager.get_config_sync(section, None, {})
        if isinstance(section_cfg, dict):
            merged = deep_merge_dict(merged, section_cfg)
    if isinstance(config, dict):
        merged = deep_merge_dict(merged, config)
    return merged

