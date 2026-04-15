#!/usr/bin/env python3
"""
一键升级闭环执行脚本

用途：
1) 调用后端 /commander/upgrade/run
2) 输出每个阶段结果
3) 快速给出是否通过与回退动作
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict
from urllib import request


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=90) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except Exception:
        return {"success": False, "message": "invalid_json_response", "raw": body}


def main() -> int:
    base = "http://127.0.0.1:8000/api/v1/modules/commander/upgrade/run"
    symbol = "BTC/USDT"
    if len(sys.argv) > 1 and str(sys.argv[1]).strip():
        symbol = str(sys.argv[1]).strip()
    payload = {
        "symbol": symbol,
        "trigger_optimize": True,
        "force_account_sync": True,
        "auto_fallback_to_semi": True,
    }
    try:
        out = post_json(base, payload)
    except Exception as e:
        print(f"[FAILED] 请求失败: {e}")
        return 2

    ok = bool(out.get("success"))
    data = out.get("data") if isinstance(out, dict) else None
    if not isinstance(data, dict):
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    print("=" * 76)
    print(f"一键升级闭环结果: {'PASS' if ok else 'FAIL'}")
    print(f"symbol={data.get('symbol')}  mode={data.get('mode')}  fallback={data.get('fallback_action')}")
    print(f"elapsed_sec={data.get('elapsed_sec')}")
    print("-" * 76)
    stages = data.get("stages") or []
    for i, st in enumerate(stages, start=1):
        name = st.get("name")
        st_ok = bool(st.get("ok"))
        print(f"{i:02d}. [{'OK' if st_ok else 'X '}] {name}")
    print("=" * 76)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

