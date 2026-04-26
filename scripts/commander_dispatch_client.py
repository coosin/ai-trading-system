#!/usr/bin/env python3
"""
Commander dispatch 调用器：
- 先走同步（可配置 timeout_sec）
- 若超时自动降级为 async_mode=true
- 轮询 /commander/dispatch/jobs/{job_id} 直到完成/失败/超时

用法示例：
  python3 scripts/commander_dispatch_client.py "请返回当前系统运行摘要"
  DISPATCH_BASE=http://127.0.0.1:8000 python3 scripts/commander_dispatch_client.py "检查账户与风险状态" --source openclaw
  OPENCLAW_API_TOKEN=xxxx python3 scripts/commander_dispatch_client.py "系统巡检" --source openclaw
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


def _build_headers(token: Optional[str] = None) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


def _post_json(url: str, payload: Dict[str, Any], timeout: float, token: Optional[str] = None) -> Tuple[int, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = _build_headers(token)
    headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8", errors="replace")


def _get_json(url: str, timeout: float, token: Optional[str] = None) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers=_build_headers(token))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8", errors="replace")


def _parse_json(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"raw": data}
    except Exception:
        return {"raw": raw}


def _pretty(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Commander dispatch 同步优先 + 异步兜底客户端")
    parser.add_argument("message", help="要发送给 commander 的消息")
    parser.add_argument("--base-url", default=os.environ.get("DISPATCH_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--source", default="control_hub")
    parser.add_argument("--sync-timeout-sec", type=float, default=8.0)
    parser.add_argument("--poll-interval-sec", type=float, default=1.2)
    parser.add_argument("--poll-timeout-sec", type=float, default=120.0)
    parser.add_argument(
        "--token",
        default=os.environ.get("OPENCLAW_API_TOKEN", ""),
        help="Bearer token. 默认读取 OPENCLAW_API_TOKEN。",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = args.token.strip() or None
    dispatch_url = f"{base}/api/v1/modules/commander/dispatch"
    sync_payload = {
        "message": args.message,
        "source": args.source,
        "timeout_sec": float(args.sync_timeout_sec),
    }

    print(f"[INFO] dispatch target: {dispatch_url}")
    print(f"[INFO] auth: {'bearer token enabled' if token else 'no token (may fail with 401/403)'}")
    print(f"[INFO] sync try: timeout_sec={sync_payload['timeout_sec']}")
    try:
        code, body = _post_json(
            dispatch_url,
            sync_payload,
            timeout=max(2.0, args.sync_timeout_sec + 2.0),
            token=token,
        )
        data = _parse_json(body)
        if code < 400 and data.get("success") and data.get("status") != "timeout":
            print("[OK] sync dispatch success")
            print(_pretty(data))
            return 0
        if data.get("status") != "timeout":
            print("[WARN] sync dispatch returned non-timeout response, stop fallback")
            print(_pretty(data))
            return 1
        print("[WARN] sync dispatch timeout, fallback to async")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        data = _parse_json(body)
        if data.get("status") != "timeout":
            print(f"[ERR] sync dispatch HTTP {e.code}")
            print(_pretty(data))
            return 1
        print("[WARN] sync dispatch HTTP timeout semantics, fallback to async")
    except Exception as e:
        print(f"[WARN] sync dispatch network/transport issue, fallback to async: {e}")

    async_payload = {
        "message": args.message,
        "source": args.source,
        "async_mode": True,
    }
    try:
        code, body = _post_json(dispatch_url, async_payload, timeout=10.0, token=token)
        data = _parse_json(body)
        if code >= 400 or not data.get("success") or not data.get("job_id"):
            print("[ERR] async dispatch enqueue failed")
            print(_pretty(data))
            return 1
        job_id = str(data["job_id"])
    except urllib.error.HTTPError as e:
        print(f"[ERR] async dispatch HTTP {e.code}")
        print(e.read().decode("utf-8", errors="replace"))
        return 1
    except Exception as e:
        print(f"[ERR] async dispatch request failed: {e}")
        return 1

    job_url = f"{base}/api/v1/modules/commander/dispatch/jobs/{job_id}"
    print(f"[INFO] async accepted: job_id={job_id}")
    print(f"[INFO] polling: {job_url}")

    deadline = time.time() + max(5.0, args.poll_timeout_sec)
    while time.time() < deadline:
        try:
            _, body = _get_json(job_url, timeout=10.0, token=token)
            data = _parse_json(body)
            item = data.get("data") if isinstance(data.get("data"), dict) else {}
            status = str(item.get("status") or "")
            if status in {"queued", "running"}:
                print(f"[INFO] job status={status}")
            elif status == "completed":
                print("[OK] async dispatch completed")
                print(_pretty(data))
                return 0
            elif status == "failed":
                print("[ERR] async dispatch failed")
                print(_pretty(data))
                return 1
            else:
                print("[WARN] unexpected polling payload")
                print(_pretty(data))
                return 1
        except Exception as e:
            print(f"[WARN] poll failed once: {e}")
        time.sleep(max(0.3, args.poll_interval_sec))

    print("[ERR] async dispatch polling timeout")
    print(f"[HINT] query manually: {job_url}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
