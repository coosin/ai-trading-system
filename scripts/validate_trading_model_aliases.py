#!/usr/bin/env python3
"""
Validate CLIProxyAPI trading model aliases end-to-end.

Checks:
- /v1/models exposes the required logical aliases
- aliases marked `ok` return exactly `OK`
- aliases marked `json` return parseable JSON matching {"ok": true}
- aliases marked `reasoning_ok` return `OK` in either message content or reasoning

Usage:
  python3 scripts/validate_trading_model_aliases.py
  CLI_PROXY_API_KEY=sk-... python3 scripts/validate_trading_model_aliases.py
  python3 scripts/validate_trading_model_aliases.py --base-url http://127.0.0.1:8317/v1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "http://127.0.0.1:8317/v1"
DEFAULT_KEY_ENV = "CLI_PROXY_API_KEY"
DEFAULT_EXPECTATIONS_PATH = REPO_ROOT / "config" / "trading_model_alias_expectations.json"
RETRYABLE_HTTP_CODES = {408, 409, 429, 500, 502, 503, 504}


def _load_dotenv_if_present(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _request_json(
    url: str,
    api_key: str,
    payload: dict[str, Any] | None,
    timeout: float,
    retries: int = 2,
    retry_backoff_sec: float = 1.5,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "openclaw-trading-alias-validator/1.0",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
            return json.loads(body)
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in RETRYABLE_HTTP_CODES or attempt >= retries:
                raise
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                raise
        time.sleep(retry_backoff_sec * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unexpected request retry state")


def _load_expectations(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_aliases(expectations: dict[str, Any]) -> list[str]:
    if expectations:
        return list(expectations.keys())
    return ["trading-fast", "trading-json", "trading-reasoning", "trading-fallback"]


def _extract_message(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing choices[0]")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("missing choices[0].message")
    return message


def _extract_message_content(payload: dict[str, Any]) -> str:
    message = _extract_message(payload)
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("missing message.content")
    return content


def _validate_exact_ok(
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    expected_response_model: str = "",
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly OK"}],
        "temperature": 0,
        "max_tokens": 8,
    }
    response = _request_json(f"{base_url}/chat/completions", api_key, payload, timeout)
    content = _extract_message_content(response).strip()
    if content != "OK":
        raise ValueError(f"{model} unexpected content: {content!r}")
    actual_model = str(response.get("model") or "")
    if expected_response_model and actual_model != expected_response_model:
        raise ValueError(
            f"{model} response model drift: expected {expected_response_model!r}, got {actual_model!r}"
        )
    return {
        "model": actual_model,
        "content": content,
        "finish_reason": ((response.get("choices") or [{}])[0]).get("finish_reason"),
    }


def _validate_json_alias(
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    expected_response_model: str = "",
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": 'Return exactly {"ok":true} as JSON.'}],
        "temperature": 0,
        "max_tokens": 32,
    }
    response = _request_json(f"{base_url}/chat/completions", api_key, payload, timeout)
    content = _extract_message_content(response).strip()
    parsed = json.loads(content)
    if parsed != {"ok": True}:
        raise ValueError(f"{model} unexpected JSON payload: {parsed!r}")
    actual_model = str(response.get("model") or "")
    if expected_response_model and actual_model != expected_response_model:
        raise ValueError(
            f"{model} response model drift: expected {expected_response_model!r}, got {actual_model!r}"
        )
    return {
        "model": actual_model,
        "content": content,
        "parsed": parsed,
        "finish_reason": ((response.get("choices") or [{}])[0]).get("finish_reason"),
    }


def _validate_reasoning_ok(
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    expected_response_model: str = "",
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly OK"}],
        "temperature": 0,
        "max_tokens": 32,
    }
    response = _request_json(f"{base_url}/chat/completions", api_key, payload, timeout)
    message = _extract_message(response)
    content = message.get("content")
    reasoning = message.get("reasoning")
    parts = []
    if isinstance(content, str):
        parts.append(content.strip())
    if isinstance(reasoning, str):
        parts.append(reasoning.strip())
    joined = "\n".join(part for part in parts if part)
    if "OK" not in joined:
        raise ValueError(f"{model} unexpected reasoning/content payload: {joined!r}")
    actual_model = str(response.get("model") or "")
    if expected_response_model and actual_model != expected_response_model:
        raise ValueError(
            f"{model} response model drift: expected {expected_response_model!r}, got {actual_model!r}"
        )
    return {
        "model": actual_model,
        "content": content,
        "reasoning": reasoning,
        "finish_reason": ((response.get("choices") or [{}])[0]).get("finish_reason"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate CLIProxyAPI trading model aliases")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--api-key", default="")
    ap.add_argument("--api-key-env", default=DEFAULT_KEY_ENV)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--skip-completions", action="store_true")
    ap.add_argument("--output-json", action="store_true")
    ap.add_argument("--expectations-file", default=str(DEFAULT_EXPECTATIONS_PATH))
    args = ap.parse_args()

    _load_dotenv_if_present(REPO_ROOT / ".env")
    expectations = _load_expectations(Path(args.expectations_file))

    api_key = (args.api_key or os.getenv(str(args.api_key_env), "")).strip()
    if not api_key:
        print(f"ERROR: missing API key. Set --api-key or env {args.api_key_env}.", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    report: dict[str, Any] = {
        "base_url": base_url,
        "aliases": {},
        "checks": [],
    }
    exit_code = 0

    try:
        models_payload = _request_json(f"{base_url}/models", api_key, None, args.timeout)
        data = models_payload.get("data")
        if not isinstance(data, list):
            raise ValueError("/models missing data[]")
        present = {
            str(item.get("id")): str(item.get("owned_by") or "")
            for item in data
            if isinstance(item, dict) and item.get("id")
        }
        for alias in _expected_aliases(expectations):
            ok = alias in present
            expected_owner = str((expectations.get(alias) or {}).get("expected_owner") or "")
            actual_owner = present.get(alias, "")
            if ok and expected_owner and actual_owner != expected_owner:
                ok = False
            detail = {
                "present": alias in present,
                "owned_by": actual_owner,
                "expected_owner": expected_owner,
            }
            report["aliases"][alias] = detail
            report["checks"].append({"name": f"models:{alias}", "ok": ok, "detail": detail})
            if not ok:
                exit_code = 1
    except Exception as exc:
        report["checks"].append({"name": "models", "ok": False, "detail": str(exc)})
        exit_code = 1

    if not args.skip_completions and exit_code == 0:
        validators = {
            "ok": _validate_exact_ok,
            "json": _validate_json_alias,
            "reasoning_ok": _validate_reasoning_ok,
        }
        for alias in _expected_aliases(expectations):
            try:
                validation_kind = str((expectations.get(alias) or {}).get("validation") or "ok")
                fn = validators.get(validation_kind)
                if fn is None:
                    raise ValueError(f"unsupported validation kind: {validation_kind}")
                expected_response_model = str(
                    (expectations.get(alias) or {}).get("expected_response_model") or ""
                )
                detail = fn(
                    base_url,
                    api_key,
                    alias,
                    args.timeout,
                    expected_response_model=expected_response_model,
                )
                if expected_response_model:
                    detail["expected_response_model"] = expected_response_model
                report["checks"].append({"name": f"completion:{alias}", "ok": True, "detail": detail})
            except urllib.error.HTTPError as exc:
                report["checks"].append(
                    {"name": f"completion:{alias}", "ok": False, "detail": f"HTTP {exc.code}: {exc.reason}"}
                )
                exit_code = 1
            except Exception as exc:
                report["checks"].append({"name": f"completion:{alias}", "ok": False, "detail": str(exc)})
                exit_code = 1

    if args.output_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code

    print(f"[base_url] {base_url}")
    for item in report["checks"]:
        tag = "OK " if item.get("ok") else "FAIL"
        print(f"[{tag}] {item.get('name')}: {item.get('detail')}")
    print("TRADING_MODEL_ALIASES=PASS" if exit_code == 0 else "TRADING_MODEL_ALIASES=FAIL")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
