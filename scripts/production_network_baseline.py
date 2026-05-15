#!/usr/bin/env python3
"""
Production network baseline guard for OpenClaw（裸金属 / 本机生产为主）。

1) Clash（若存在 /etc/clash/config.yaml）：mode/DNS/OKX 过滤等基线；--apply 时写回并可选重启。
2) 公网连通性探针：在**本机 Python 进程内执行**（与当前生产进程同网络栈）。

Usage:
  python3 scripts/production_network_baseline.py --check-only
  python3 scripts/production_network_baseline.py --apply

无 /etc/clash/config.yaml 且为 check-only：跳过 Clash 文件与 selector 硬门禁，仍跑本机探针。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.request import Request, urlopen

import yaml


REPO = Path(__file__).resolve().parents[1]
CLASH_CONFIG = Path("/etc/clash/config.yaml")


def run(
    cmd: List[str], check: bool = True, timeout: float | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(REPO), check=check, text=True, capture_output=True, timeout=timeout)


def enforce_clash_config(apply: bool) -> Dict[str, Any]:
    if not CLASH_CONFIG.exists():
        if apply:
            raise RuntimeError(f"clash config not found: {CLASH_CONFIG}")
        return {
            "skipped": True,
            "reason": "clash_config_missing",
            "path": str(CLASH_CONFIG),
            "mode": None,
            "dns_listen": None,
            "dns_enhanced_mode": None,
            "okx_filter": None,
        }

    with CLASH_CONFIG.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    dns = cfg.get("dns") or {}
    cfg["mode"] = "Rule"
    dns["enable"] = True
    dns["enhanced-mode"] = "fake-ip"
    dns["fake-ip-range"] = dns.get("fake-ip-range", "198.18.0.1/16")
    dns["listen"] = dns.get("listen", "0.0.0.0:1053")

    # Prefer 1.1.1.1 first: CN/ISP resolvers often return awscn.okpool.top -> 169.254.0.2 for OKX,
    # which breaks TLS/routing; Cloudflare DNS returns the real Cloudflare CDN chain.
    nameserver = dns.get("nameserver") or []
    for ns in ["1.1.1.1", "8.8.8.8", "119.29.29.29", "223.5.5.5"]:
        if ns not in nameserver:
            nameserver.append(ns)
    dns["nameserver"] = nameserver

    fallback = dns.get("fallback") or []
    for ns in [
        "tls://1.1.1.1:853",
        "tls://dns.google:853",
        "https://dns.alidns.com/dns-query",
        "https://doh.pub/dns-query",
    ]:
        if ns not in fallback:
            fallback.append(ns)
    dns["fallback"] = fallback

    fake_filter = dns.get("fake-ip-filter") or []
    for item in ["+.lan", "+.local", "localhost", "+.okx.com", "+.okex.com"]:
        if item not in fake_filter:
            fake_filter.append(item)
    dns["fake-ip-filter"] = fake_filter

    nsp = dns.get("nameserver-policy") or {}
    # Do not use 119/223/114 for OKX: many return poisoned/hijacked records in CN networks.
    nsp["+.okx.com"] = "1.1.1.1"
    nsp["+.okex.com"] = "1.1.1.1"
    dns["nameserver-policy"] = nsp
    cfg["dns"] = dns

    if apply:
        with CLASH_CONFIG.open("w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    return {
        "mode": cfg.get("mode"),
        "dns_listen": dns.get("listen"),
        "dns_enhanced_mode": dns.get("enhanced-mode"),
        "okx_filter": ("+.okx.com" in fake_filter and "+.okex.com" in fake_filter),
    }


def restart_clash_if_needed(apply: bool) -> None:
    if not apply:
        return
    run(["systemctl", "restart", "clash"])


def set_clash_selector_auto(apply: bool) -> Dict[str, Any]:
    def _wait_controller(timeout_s: float = 20.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                with urlopen("http://127.0.0.1:9090/proxies", timeout=3):
                    return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("clash controller not ready on 127.0.0.1:9090")

    _wait_controller()
    if apply:
        req = Request(
            "http://127.0.0.1:9090/proxies/%F0%9F%9A%80%20%E8%8A%82%E7%82%B9%E9%80%89%E6%8B%A9",
            method="PUT",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"name": "♻️ 自动选择"}).encode("utf-8"),
        )
        with urlopen(req, timeout=10):
            pass

    with urlopen("http://127.0.0.1:9090/proxies", timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    sel = data.get("proxies", {}).get("🚀 节点选择", {})
    auto = data.get("proxies", {}).get("♻️ 自动选择", {})
    return {"selector_now": sel.get("now"), "auto_now": auto.get("now")}


def verify_compose_proxy_env() -> Dict[str, Any]:
    """仓库已移除 Docker Compose；保留字段名供下游 JSON 兼容，恒为跳过。"""
    return {"ok": True, "skipped": True, "reason": "compose_removed_bare_metal_only"}


_RUNTIME_PROBE_SCRIPT = r"""
import os, json, time, urllib.request
out = {"env": {}, "probes": {}}
for k in ["OPENCLAW_HTTP_PROXY","OPENCLAW_HTTPS_PROXY","OPENCLAW_ALL_PROXY","NO_PROXY"]:
    out["env"][k] = os.getenv(k, "")
NR = int(os.environ.get("OPENCLAW_PROBE_ROUNDS", "6"))
NR = max(2, min(8, NR))
TO = float(os.environ.get("OPENCLAW_PROBE_URL_TIMEOUT", "3.5"))
TO = max(1.2, min(10.0, TO))
targets = {
    "okx_time": "https://www.okx.com/api/v5/public/time",
    "binance_time": "https://api.binance.com/api/v3/time",
    "coingecko_ping": "https://api.coingecko.com/api/v3/ping",
    "coinbase_time": "https://api.coinbase.com/v2/time",
    "kraken_time": "https://api.kraken.com/0/public/Time",
}
for name, url in targets.items():
    ok = 0
    fail = 0
    last = None
    for _ in range(NR):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "network-baseline-probe/1.0"})
            with urllib.request.urlopen(req, timeout=TO) as resp:
                last = int(getattr(resp, "status", 200) or 200)
            if last < 400:
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        time.sleep(0.12)
    out["probes"][name] = {"ok": ok, "fail": fail, "last_status": last}
print(json.dumps(out, ensure_ascii=False))
"""


def runtime_probe(*, quick: bool = False) -> Dict[str, Any]:
    """本机 Python 探针（与裸金属生产一致）。"""
    r2 = run([sys.executable, "-c", _RUNTIME_PROBE_SCRIPT], check=False)
    if r2.returncode == 0 and (r2.stdout or "").strip():
        try:
            out = json.loads(r2.stdout.strip())
            out["probe_mode"] = "host_python"
            return out
        except json.JSONDecodeError:
            pass
    return {
        "error": "runtime_probe_failed",
        "host_rc": r2.returncode,
        "host_stderr": (r2.stderr or "")[:800],
        "probes": {},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="enforce baseline")
    parser.add_argument("--check-only", action="store_true", help="check only")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="fewer outbound probe rounds (faster; thresholds relaxed slightly)",
    )
    args = parser.parse_args()
    apply = args.apply and not args.check_only
    if args.quick:
        os.environ.setdefault("OPENCLAW_PROBE_ROUNDS", "2")
        os.environ.setdefault("OPENCLAW_PROBE_URL_TIMEOUT", "2.0")

    report: Dict[str, Any] = {"apply": apply}
    report["clash_config"] = enforce_clash_config(apply=apply)
    clash_skipped = bool(report["clash_config"].get("skipped"))
    restart_clash_if_needed(apply=apply)
    if clash_skipped:
        report["clash_selector"] = {
            "skipped": True,
            "selector_now": None,
            "auto_now": None,
        }
    else:
        report["clash_selector"] = set_clash_selector_auto(apply=apply)
    report["compose_env"] = verify_compose_proxy_env()
    report["runtime"] = runtime_probe(quick=bool(args.quick))

    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Operator hint: empty proxy env + failing probes usually means wrong network namespace or missing TUN.
    _rt = report.get("runtime") or {}
    _env = _rt.get("env") or {}
    _prox_empty = not any(str(_env.get(k) or "").strip() for k in ("OPENCLAW_HTTP_PROXY", "OPENCLAW_HTTPS_PROXY", "OPENCLAW_ALL_PROXY"))
    _okx_ok = int((_rt.get("probes") or {}).get("okx_time", {}).get("ok", 0) or 0)
    if _prox_empty and _okx_ok < 1 and not _rt.get("error"):
        print(
            "\nRUNTIME_HINT: 探针进程未设置 OPENCLAW_*_PROXY，urllib 走系统直连。"
            "若 OKX 应经宿主机 Clash：在运行 baseline 的同一 shell 导出与交易进程一致的代理变量，"
            "或启用宿主机 TUN（见 deploy/HOST_CLASH_EGRESS.md）。",
            file=sys.stderr,
        )

    # hard pass criteria for production baseline
    runtime = (report["runtime"] or {}).get("probes") or {}
    hard_fail: List[str] = []
    _nr = int(os.environ.get("OPENCLAW_PROBE_ROUNDS", "6"))
    _min_ok = 4 if _nr >= 5 else (3 if _nr >= 3 else 2)
    if not clash_skipped:
        if report["clash_config"].get("mode") != "Rule":
            hard_fail.append("clash mode not Rule")
        if report["clash_selector"].get("selector_now") != "♻️ 自动选择":
            hard_fail.append("selector not auto")
    if not report["compose_env"]["ok"]:
        if not report["compose_env"].get("skipped"):
            hard_fail.append("compose proxy env missing")
    if report["runtime"].get("error"):
        hard_fail.append(f"runtime probe: {report['runtime'].get('error')}")
    if args.quick:
        if runtime.get("okx_time", {}).get("ok", 0) < 1:
            hard_fail.append("okx stability too low (quick mode)")
    else:
        if runtime.get("okx_time", {}).get("ok", 0) < _min_ok:
            hard_fail.append("okx stability too low")
        if runtime.get("coingecko_ping", {}).get("ok", 0) < _min_ok:
            hard_fail.append("coingecko stability too low")
        if runtime.get("coinbase_time", {}).get("ok", 0) < _min_ok:
            hard_fail.append("coinbase stability too low")
        if runtime.get("kraken_time", {}).get("ok", 0) < _min_ok:
            hard_fail.append("kraken stability too low")

    if hard_fail:
        print("\nBASELINE_CHECK=FAIL")
        for item in hard_fail:
            print("-", item)
        return 2

    print("\nBASELINE_CHECK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

