#!/usr/bin/env python3
"""
生成 / 同步统一配置文件：
  - config/openclaw.yml（带头注释）
  - src/modules/core/openclaw.embedded.yml（内置兜底，无头注释）
  - test_config/openclaw.yml（与主文件同步，供测试）

当 ConfigManager.DEFAULT_CONFIG 非空时：以其为底并与现有 config/openclaw.yml 深度合并。
当 DEFAULT 已清空时：以 config/openclaw.yml 为主；若不存在则读 openclaw.embedded.yml。
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from src.modules.core.config_manager import ConfigManager  # noqa: E402

HEADER = """# =============================================================================
# OpenClaw 统一可调配置（主文件）
# -----------------------------------------------------------------------------
# 合并优先级（后者覆盖前者）：
#   1) openclaw.embedded.yml（与源码同目录，内置兜底）
#   2) 各配置目录：default.* < openclaw.* < 其它片段 < local.*
#   3) 环境变量 OPENCLAW__section__key__nested
#
# 密钥仅放在仓库根目录 .env，勿写入本文件。
# 本机覆盖：复制 config/openclaw.local.example.yml 为 config/local.yml（已 gitignore）。
#
# 修改后运行： python scripts/generate_openclaw_yaml.py
# 以同步 embedded 与 test_config/openclaw.yml。
# =============================================================================
"""


def _merge_overlay_inplace(base: dict, overlay: dict) -> None:
    for k, v in overlay.items():
        if str(k).startswith("_"):
            continue
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _merge_overlay_inplace(base[k], v)
        else:
            base[k] = copy.deepcopy(v)


def main() -> int:
    openclaw_path = ROOT / "config" / "openclaw.yml"
    emb_read = ROOT / "src" / "modules" / "core" / "openclaw.embedded.yml"

    if ConfigManager.DEFAULT_CONFIG:
        base = copy.deepcopy(ConfigManager.DEFAULT_CONFIG)
        if openclaw_path.is_file():
            with open(openclaw_path, encoding="utf-8") as f:
                overlay = yaml.safe_load(f) or {}
            if isinstance(overlay, dict):
                _merge_overlay_inplace(base, overlay)
    else:
        if openclaw_path.is_file():
            with open(openclaw_path, encoding="utf-8") as f:
                base = yaml.safe_load(f) or {}
            if not isinstance(base, dict):
                base = {}
        elif emb_read.is_file():
            with open(emb_read, encoding="utf-8") as f:
                base = yaml.safe_load(f) or {}
            if not isinstance(base, dict):
                base = {}
        else:
            print("ERROR: no DEFAULT_CONFIG, no openclaw.yml, no embedded", file=sys.stderr)
            return 1

    body = yaml.dump(
        base,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )
    openclaw_path.parent.mkdir(parents=True, exist_ok=True)
    openclaw_path.write_text(HEADER.rstrip() + "\n\n" + body, encoding="utf-8")
    emb_write = ROOT / "src" / "modules" / "core" / "openclaw.embedded.yml"
    emb_write.write_text(body, encoding="utf-8")
    test_oc = ROOT / "test_config" / "openclaw.yml"
    test_oc.parent.mkdir(parents=True, exist_ok=True)
    test_oc.write_text(HEADER.rstrip() + "\n\n" + body, encoding="utf-8")
    print("OK:", openclaw_path)
    print("OK:", emb_write)
    print("OK:", test_oc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
