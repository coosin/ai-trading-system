"""YAML transforms for scripts/clash_dns_fake_ip_filter_experiment.py (no live Clash)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "clash_dns_minimal.yaml"


def _run_script(cfg: Path, *args: str) -> int:
    import subprocess
    import sys

    script = REPO / "scripts" / "clash_dns_fake_ip_filter_experiment.py"
    # 父级参数 --config 必须出现在子命令之前，否则 argparse 会忽略并落到默认 /etc/clash/config.yaml
    p = subprocess.run(
        [sys.executable, str(script), "--config", str(cfg), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    return int(p.returncode)


def test_strip_okx_removes_okx_entries(tmp_path: Path) -> None:
    dst = tmp_path / "c.yaml"
    shutil.copy(FIXTURE, dst)
    assert _run_script(dst, "strip-okx") == 0
    cfg = yaml.safe_load(dst.read_text(encoding="utf-8"))
    filt = (cfg.get("dns") or {}).get("fake-ip-filter") or []
    assert "+.okx.com" not in filt
    assert "+.okex.com" not in filt
    assert "+.lan" in filt


def test_disable_dns_flips_enable(tmp_path: Path) -> None:
    dst = tmp_path / "c.yaml"
    shutil.copy(FIXTURE, dst)
    assert _run_script(dst, "disable-dns") == 0
    cfg = yaml.safe_load(dst.read_text(encoding="utf-8"))
    assert (cfg.get("dns") or {}).get("enable") is False
    assert _run_script(dst, "enable-dns") == 0
    cfg2 = yaml.safe_load(dst.read_text(encoding="utf-8"))
    assert (cfg2.get("dns") or {}).get("enable") is True


def test_set_enhanced_mode(tmp_path: Path) -> None:
    dst = tmp_path / "c.yaml"
    shutil.copy(FIXTURE, dst)
    assert _run_script(dst, "set-enhanced-mode", "redir-host") == 0
    cfg = yaml.safe_load(dst.read_text(encoding="utf-8"))
    assert (cfg.get("dns") or {}).get("enhanced-mode") == "redir-host"
