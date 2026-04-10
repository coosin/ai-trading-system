#!/usr/bin/env python3
"""
Production network baseline guard for OpenClaw.

What it does:
1) Enforce and verify Clash core baseline:
   - mode: Rule
   - DNS safe defaults (fake-ip, listen 1053, okx filters/policy)
   - main selector set to auto
2) Verify docker compose proxy env baseline.
3) Validate container runtime env and API connectivity probes.

Usage:
  python3 scripts/production_network_baseline.py --apply
  python3 scripts/production_network_baseline.py --check-only
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


def run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(REPO), check=check, text=True, capture_output=True)


def enforce_clash_config(apply: bool) -> Dict[str, Any]:
    if not CLASH_CONFIG.exists():
        raise RuntimeError(f"clash config not found: {CLASH_CONFIG}")

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
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    required = [
        "OPENCLAW_HTTP_PROXY",
        "OPENCLAW_HTTPS_PROXY",
        "OPENCLAW_ALL_PROXY",
        "host.docker.internal:7890",
        "NO_PROXY=localhost,127.0.0.1,redis",
    ]
    missing = [k for k in required if k not in compose]
    return {"ok": not missing, "missing": missing}


def runtime_probe() -> Dict[str, Any]:
    script = r"""
import os, requests, json, time
proxy = os.getenv("OPENCLAW_HTTP_PROXY")
out = {"env": {}, "probes": {}}
for k in ["OPENCLAW_HTTP_PROXY","OPENCLAW_HTTPS_PROXY","OPENCLAW_ALL_PROXY","NO_PROXY"]:
    out["env"][k] = os.getenv(k, "")
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
    for _ in range(6):
        try:
            r = requests.get(url, proxies={"http": proxy, "https": proxy}, timeout=8, verify=True)
            last = r.status_code
            if r.status_code < 400:
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        time.sleep(0.15)
    out["probes"][name] = {"ok": ok, "fail": fail, "last_status": last}
print(json.dumps(out, ensure_ascii=False))
"""
    r = run(["docker", "exec", "-i", "openclaw-trading", "python", "-c", script], check=True)
    return json.loads(r.stdout.strip() or "{}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="enforce baseline")
    parser.add_argument("--check-only", action="store_true", help="check only")
    args = parser.parse_args()
    apply = args.apply and not args.check_only

    report: Dict[str, Any] = {"apply": apply}
    report["clash_config"] = enforce_clash_config(apply=apply)
    restart_clash_if_needed(apply=apply)
    report["clash_selector"] = set_clash_selector_auto(apply=apply)
    report["compose_env"] = verify_compose_proxy_env()
    report["runtime"] = runtime_probe()

    print(json.dumps(report, ensure_ascii=False, indent=2))

    # hard pass criteria for production baseline
    runtime = report["runtime"]["probes"]
    hard_fail = []
    if report["clash_config"]["mode"] != "Rule":
        hard_fail.append("clash mode not Rule")
    if report["clash_selector"].get("selector_now") != "♻️ 自动选择":
        hard_fail.append("selector not auto")
    if not report["compose_env"]["ok"]:
        hard_fail.append("compose proxy env missing")
    if runtime.get("okx_time", {}).get("ok", 0) < 4:
        hard_fail.append("okx stability too low")
    if runtime.get("coingecko_ping", {}).get("ok", 0) < 4:
        hard_fail.append("coingecko stability too low")
    if runtime.get("coinbase_time", {}).get("ok", 0) < 4:
        hard_fail.append("coinbase stability too low")
    if runtime.get("kraken_time", {}).get("ok", 0) < 4:
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

