#!/usr/bin/env python3
"""
Clash / mihomo：对 dns.fake-ip-filter 做 A/B 实验（仅改 YAML，不自动重启内核）。

典型用途：暂时从 fake-ip-filter 中移除 +.okx.com / +.okex.com，重启 Clash 后运行
`scripts/network_connectivity_smoke.py`，与移除前对比 DNS/TCP/HTTPS 是否改善。

注意：
- fake-ip-filter 中列出的是「不使用 fake-ip、走真实解析」的域名；移除后 OKX 会走 fake-ip 映射，
  结果可能变好也可能变差，需以你环境实测为准。
- 修改系统配置需要写权限：通常 `sudo python3 ...`。

用法:
  sudo python3 scripts/clash_dns_fake_ip_filter_experiment.py show --config /etc/clash/config.yaml
  sudo python3 scripts/clash_dns_fake_ip_filter_experiment.py backup --config /etc/clash/config.yaml
  sudo python3 scripts/clash_dns_fake_ip_filter_experiment.py strip-okx --config /etc/clash/config.yaml
  # 然后: sudo systemctl restart clash   （或你的 mihomo 重启方式）
  python3 scripts/network_connectivity_smoke.py
  sudo python3 scripts/clash_dns_fake_ip_filter_experiment.py restore --config /etc/clash/config.yaml
  # 或: ... restore --config /etc/clash/config.yaml --from-backup /path/to/...backup-TS
  sudo python3 scripts/clash_dns_fake_ip_filter_experiment.py disable-dns --config /etc/clash/config.yaml
  sudo python3 scripts/clash_dns_fake_ip_filter_experiment.py enable-dns --config /etc/clash/config.yaml
  sudo python3 scripts/clash_dns_fake_ip_filter_experiment.py set-enhanced-mode redir-host --config /etc/clash/config.yaml
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIG = Path("/etc/clash/config.yaml")
MARKER = ".openclaw-dns-experiment-backup"


def _load(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save(p: Path, cfg: Dict[str, Any]) -> None:
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def cmd_show(config: Path) -> int:
    cfg = _load(config)
    dns = cfg.get("dns") or {}
    print(f"config: {config}")
    print(f"dns.enable: {dns.get('enable')}")
    print(f"dns.enhanced-mode: {dns.get('enhanced-mode')}")
    print(f"dns.fake-ip-range: {dns.get('fake-ip-range')}")
    filt = dns.get("fake-ip-filter") or []
    print(f"dns.fake-ip-filter ({len(filt)} items):")
    for x in filt[:60]:
        print(f"  - {x}")
    if len(filt) > 60:
        print(f"  ... ({len(filt) - 60} more)")
    return 0


def cmd_backup(config: Path) -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = config.parent / f"{config.name}{MARKER}-{ts}"
    shutil.copy2(config, dst)
    # 记录最近一次备份路径，供 restore 默认使用
    tag = config.parent / f"{config.name}{MARKER}-LATEST"
    tag.write_text(str(dst.resolve()) + "\n", encoding="utf-8")
    print(f"backup written: {dst}")
    print(f"latest pointer: {tag}")
    return 0


def _latest_backup(config: Path) -> Path | None:
    tag = config.parent / f"{config.name}{MARKER}-LATEST"
    if not tag.is_file():
        return None
    p = Path(tag.read_text(encoding="utf-8").strip())
    return p if p.is_file() else None


def cmd_restore(config: Path, backup: Path | None) -> int:
    src = backup or _latest_backup(config)
    if not src or not src.is_file():
        print("ERROR: no backup path; run backup first or pass --from-backup", file=sys.stderr)
        return 2
    shutil.copy2(src, config)
    print(f"restored {config} <- {src}")
    return 0


def cmd_strip_okx(config: Path) -> int:
    cfg = _load(config)
    dns = dict(cfg.get("dns") or {})
    filt = list(dns.get("fake-ip-filter") or [])
    remove = {"+.okx.com", "+.okex.com", "okx.com", "okex.com"}
    before = len(filt)
    filt2 = [x for x in filt if str(x).strip() not in remove]
    removed = before - len(filt2)
    dns["fake-ip-filter"] = filt2
    cfg["dns"] = dns
    _save(config, cfg)
    print(f"strip-okx: removed {removed} fake-ip-filter entries (matched: {sorted(remove)})")
    print("NEXT: restart clash/mihomo, then run: python3 scripts/network_connectivity_smoke.py")
    return 0


def cmd_strip_all_fake_ip_filter(config: Path) -> int:
    """Aggressive: clear entire fake-ip-filter list (for A/B only)."""
    cfg = _load(config)
    dns = dict(cfg.get("dns") or {})
    before = dns.get("fake-ip-filter") or []
    dns["fake-ip-filter"] = []
    cfg["dns"] = dns
    _save(config, cfg)
    print(f"strip-all-fake-ip-filter: cleared {len(before)} entries")
    print("NEXT: restart clash/mihomo, then run network_connectivity_smoke.py")
    return 0


def cmd_disable_dns(config: Path) -> int:
    """Turn off Clash embedded DNS (dns.enable=false). Use backup/restore to roll back."""
    cfg = _load(config)
    dns = dict(cfg.get("dns") or {})
    dns["enable"] = False
    cfg["dns"] = dns
    _save(config, cfg)
    print("dns.enable=false (Clash DNS module off). NEXT: restart clash/mihomo, then: python3 scripts/network_connectivity_smoke.py --https-okx")
    return 0


def cmd_enable_dns(config: Path) -> int:
    cfg = _load(config)
    dns = dict(cfg.get("dns") or {})
    dns["enable"] = True
    cfg["dns"] = dns
    _save(config, cfg)
    print("dns.enable=true. NEXT: restart clash/mihomo, then: python3 scripts/network_connectivity_smoke.py --https-okx")
    return 0


def cmd_set_enhanced_mode(config: Path, mode: str) -> int:
    allowed = {"fake-ip", "redir-host", "normal"}
    if mode not in allowed:
        print(f"ERROR: mode must be one of {sorted(allowed)}", file=sys.stderr)
        return 2
    cfg = _load(config)
    dns = dict(cfg.get("dns") or {})
    dns["enhanced-mode"] = mode
    cfg["dns"] = dns
    _save(config, cfg)
    print(f"dns.enhanced-mode={mode}. NEXT: restart clash/mihomo, then: python3 scripts/network_connectivity_smoke.py --https-okx")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Clash fake-ip-filter DNS experiment helper")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="path to clash config yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show", help="print dns.* snapshot")
    sub.add_parser("backup", help="copy config to timestamped backup + update LATEST pointer")
    sub.add_parser("strip-okx", help="remove +.okx.com / +.okex.com from fake-ip-filter")
    sub.add_parser(
        "strip-all-filter",
        help="clear entire dns.fake-ip-filter (aggressive A/B; backup first!)",
    )
    p_rest = sub.add_parser("restore", help="restore config from backup")
    p_rest.add_argument(
        "--from-backup",
        dest="from_backup",
        type=Path,
        default=None,
        help="specific backup file (default: LATEST pointer from backup)",
    )
    sub.add_parser("disable-dns", help="set dns.enable=false (turn off Clash DNS)")
    sub.add_parser("enable-dns", help="set dns.enable=true")
    p_mode = sub.add_parser(
        "set-enhanced-mode",
        help="set dns.enhanced-mode to fake-ip | redir-host | normal",
    )
    p_mode.add_argument("mode", choices=["fake-ip", "redir-host", "normal"])

    args = ap.parse_args()
    cfg_path: Path = args.config
    if not cfg_path.is_file():
        print(f"ERROR: config not found: {cfg_path}", file=sys.stderr)
        return 2

    if args.cmd == "show":
        return cmd_show(cfg_path)
    if args.cmd == "backup":
        return cmd_backup(cfg_path)
    if args.cmd == "restore":
        return cmd_restore(cfg_path, getattr(args, "from_backup", None))
    if args.cmd == "strip-okx":
        return cmd_strip_okx(cfg_path)
    if args.cmd == "strip-all-filter":
        return cmd_strip_all_fake_ip_filter(cfg_path)
    if args.cmd == "disable-dns":
        return cmd_disable_dns(cfg_path)
    if args.cmd == "enable-dns":
        return cmd_enable_dns(cfg_path)
    if args.cmd == "set-enhanced-mode":
        return cmd_set_enhanced_mode(cfg_path, str(args.mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
