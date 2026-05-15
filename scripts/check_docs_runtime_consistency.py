#!/usr/bin/env python3
"""
Check documentation consistency against the current system.

What it checks:
- Endpoint paths mentioned in docs (*.md) exist in runtime OpenAPI.
- Quick scan of referenced scripts and local file paths.
- A small "undocumented endpoints" sample for commander surfaces.

Usage:
  python3 scripts/check_docs_runtime_consistency.py
  BASE_URL=... is not needed here; this builds OpenAPI from current code, not live HTTP.

Exit codes:
  0: OK (no blocking issues)
  2: Inconsistencies found (missing endpoints / missing referenced files)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


RE_ENDPOINT = re.compile(
    r"(?<![A-Za-z0-9_])(/(?:api|openapi\.json|docs|redoc|ws)\S*)"
)
RE_CODE_TICK = re.compile(r"`([^`]+)`")
# Third-party REST bases accidentally captured as "/api" + ".vendor.com/..."
RE_EXTERNAL_API_HOST_PATH = re.compile(r"^/api\.[^/]+/")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _normalize_path(s: str) -> str:
    s = s.strip()
    s = s.strip("`")
    s = s.rstrip("`\"'”).,;:!?，。：；）】》>")
    # Drop markdown trailing fences or emphasis leftovers
    s = s.replace("**", "")
    # Some docs use OpenAPI path-set notation like /x{,/y}; normalize to base.
    # Do NOT strip normal path params like /foo/{id}.
    if "{,/" in s:
        s = s.split("{", 1)[0]
    # Separate query so we can compare against OpenAPI base paths
    s = s.split("?", 1)[0]
    # Stop at accidental inline fragments
    for sep in ("`", '"', "'", "（", "。", "，", " "):
        if sep in s:
            s = s.split(sep, 1)[0]
    return s


def _is_wildcard_or_example(s: str) -> bool:
    if "..." in s:
        return True
    if "<" in s or ">" in s:
        return True
    return False


def _extract_endpoints_from_markdown(text: str) -> set[str]:
    out: set[str] = set()
    for raw in RE_ENDPOINT.findall(text):
        p = _normalize_path(raw)
        if not p.startswith("/"):
            continue
        if RE_EXTERNAL_API_HOST_PATH.match(p):
            # e.g. /api.deepseek.com/v1/chat/completions — not this service's OpenAPI
            continue
        if p.startswith("/docs/"):
            # markdown links like /docs/API_REFERENCE.md are repo paths, not HTTP endpoints
            continue
        if "." in p and not p.startswith(("/api", "/auth", "/health", "/metrics", "/ws")):
            # skip host-like fragments accidentally matched
            continue
        if _is_wildcard_or_example(p):
            continue
        out.add(p)
    return out


def _load_openapi_runtime(repo: Path) -> dict:
    """
    Build OpenAPI from the current code, without running uvicorn.
    Requires dependencies installed in the current environment.
    """
    # Ensure repo import works (many scripts rely on PYTHONPATH externally)
    sys.path.insert(0, str(repo))
    try:
        import asyncio  # noqa: WPS433

        from src.modules.api.server import APIServer  # noqa: WPS433
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Failed to import APIServer. Ensure you are running inside the project venv and "
            "PYTHONPATH points to repo root."
        ) from e

    async def _build() -> dict:
        server = APIServer(host="127.0.0.1", port=8000)
        await server.initialize()
        if server.app is None:  # pragma: no cover
            raise RuntimeError("APIServer.app is None after initialize()")
        return server.app.openapi()

    return asyncio.run(_build())


@dataclass
class CheckResult:
    missing_endpoints: list[str]
    missing_files: list[str]
    undocumented_commander: list[str]

    @property
    def ok(self) -> bool:
        return not self.missing_endpoints and not self.missing_files


def _strip_shell_invocation_prefix(token: str) -> str:
    """`bash scripts/foo.sh` -> `scripts/foo.sh` for path existence checks."""
    s = token.strip()
    lowered = s.lower()
    for prefix in ("bash ", "sh ", "source "):
        if lowered.startswith(prefix):
            return s[len(prefix) :].strip()
    return s


def _iter_markdown_files(repo: Path) -> Iterable[Path]:
    yield repo / "README.md"
    docs = repo / "docs"
    if docs.exists():
        yield from docs.glob("**/*.md")


def _scan_missing_local_references(repo: Path, md_path: Path, md_text: str) -> list[str]:
    """
    Heuristic: detect `scripts/foo.py`, `deploy/foo.md`, etc inside backticks,
    verify file exists relative to repo.
    """
    missing: list[str] = []
    ignore_tokens = {
        # Historical/deprecated file names intentionally mentioned as removed
        "data/config/default.yml",
        "data/config/memory.json",
        "logs/config-health.json",
        # Shorthand that should not be treated as a file path requirement
        "docs/README",
        # Removed during 2026-04-27 cleanup
        "scripts/one_click_upgrade_pipeline.py",
        "scripts/verify.py trading",
        "src/modules/api/backtest_api.py",
        "src/modules/api/enhanced_api.py",
        "src/modules/api/risk_api.py",
        # Gitignored local overlay; template is config/config.local.example.yaml
        "config/local.yaml",
    }

    for token in RE_CODE_TICK.findall(md_text):
        s = _strip_shell_invocation_prefix(token.strip())
        if not s:
            continue
        if s in ignore_tokens:
            continue
        # Ignore URLs / commands / endpoints / placeholders
        if any(
            s.startswith(prefix)
            for prefix in (
                "http://",
                "https://",
                "ws://",
                "wss://",
                "curl ",
                "python ",
                "python3 ",
                "docker ",
                "GET ",
                "POST ",
                "PUT ",
                "DELETE ",
                "PATCH ",
            )
        ):
            continue
        if s.startswith("/") or s.startswith("openapi.json"):
            continue
        if "<" in s or ">" in s:
            continue
        # Ignore patterns / globs / brace expansions
        if any(ch in s for ch in ("*", "{", "}", "[" , "]")):
            continue
        # Only check plausible repo paths
        if not (
            s.startswith(("docs/", "scripts/", "deploy/", "src/", "config/"))
            or s.endswith((".md", ".py", ".sh", ".yml", ".yaml", ".service", ".json"))
        ):
            continue
        # Avoid checking multi-line code blocks accidentally captured
        if "\n" in s or "\r" in s:
            continue
        # If token is a bare filename (no /), it is often contextual (e.g. "config.yaml"),
        # and may not be resolvable unambiguously; only check when it has a directory prefix.
        if "/" not in s and not s.startswith(("docs/", "scripts/", "deploy/", "src/", "config/")):
            continue

        # If it's a relative path without dir prefix, resolve relative to the md file.
        if s.startswith(("./", "../")):
            p = (md_path.parent / s).resolve()
        else:
            p = (repo / s).resolve()
        if not p.exists():
            missing.append(s)
    return sorted(set(missing))


def run_checks(repo: Path, openapi: dict) -> CheckResult:
    openapi_paths = set((openapi.get("paths") or {}).keys())

    mentioned_endpoints: set[str] = set()
    missing_files: set[str] = set()

    for md in _iter_markdown_files(repo):
        if not md.exists():
            continue
        text = _read_text(md)
        mentioned_endpoints |= _extract_endpoints_from_markdown(text)
        for m in _scan_missing_local_references(repo, md, text):
            missing_files.add(f"{md.relative_to(repo).as_posix()}: `{m}`")

    # Filter out known non-openapi endpoints / docs endpoints
    ignore = {
        "/docs",
        "/redoc",
        "/openapi.json",
        "/ws",
        "/api",  # prefix mention in docs
        "/api/events/ingest",  # OpenClaw side receiver endpoint (external system)
        # Non-concrete docs aliases/patterns
        "/api/v1/auth/*",
        "/api/v1/modules",
        "/api/v1/modules/commander/*",
        "/api/v1/{domain}/",
        # Runtime-first endpoints can be absent from stale snapshot exports
        "/api/v1/auth/status",
        "/api/v1/auth/write-policy",
        "/api/v1/trades/attribution/regime/health",
        # Historical removed endpoints can still appear in cleanup docs.
        "/api/v1/commander",
        "/api/v1/commander/_audit",
        "/api/v1/commander/{path}",
        "/api/v1/data-fusion/analyze",
        "/api/v1/data-fusion/analyze/{symbol}",
        "/api/v1/trade/history",
        "/api/v1/trading/history",
    }

    ignore_prefixes = (
        "/api/v5/",  # OKX upstream REST base path (external)
        "/wspri.okx.com",
        "/wspripap.okx.com",
        "/wsdexpri.okx.com",
    )

    missing_endpoints = sorted(
        p
        for p in mentioned_endpoints
        if p not in ignore
        and not any(p.startswith(pref) for pref in ignore_prefixes)
        and "okx.com" not in p
        and not p.startswith("/api/v1/modules/surface/")  # docs often mention `/.../...` generically
        and p not in openapi_paths
    )

    undocumented_commander = sorted(
        p
        for p in openapi_paths
        if p.startswith("/api/v1/modules/commander/")
        and p not in mentioned_endpoints
        and not p.startswith("/api/v1/modules/commander/memory/")  # memory endpoints are listed elsewhere
    )

    return CheckResult(
        missing_endpoints=missing_endpoints,
        missing_files=sorted(missing_files),
        undocumented_commander=undocumented_commander,
    )


def main() -> int:
    repo = _repo_root()
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--runtime",
        action="store_true",
        help="Deprecated no-op; OpenAPI is always generated from runtime code.",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON report to stdout.",
    )
    ap.add_argument(
        "--warn-only",
        action="store_true",
        help="Always exit 0 even if issues are found.",
    )
    args = ap.parse_args()

    openapi = _load_openapi_runtime(repo)
    source = "runtime"

    result = run_checks(repo, openapi)

    report = {
        "source": source,
        "openapi_paths": len((openapi.get("paths") or {}).keys()),
        "missing_endpoints_count": len(result.missing_endpoints),
        "missing_files_count": len(result.missing_files),
        "undocumented_commander_sample": result.undocumented_commander[:15],
        "missing_endpoints": result.missing_endpoints,
        "missing_files": result.missing_files,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[docs-check] openapi_source={source} paths={report['openapi_paths']}")
        if result.missing_endpoints:
            print(f"[docs-check] MISSING endpoints: {len(result.missing_endpoints)}")
            for p in result.missing_endpoints[:80]:
                print(f"  - {p}")
            if len(result.missing_endpoints) > 80:
                print("  - ...")
        if result.missing_files:
            print(f"[docs-check] MISSING referenced files: {len(result.missing_files)}")
            for p in result.missing_files[:80]:
                print(f"  - {p}")
            if len(result.missing_files) > 80:
                print("  - ...")
        if not result.missing_endpoints and not result.missing_files:
            print("[docs-check] OK: no blocking inconsistencies found.")

        if result.undocumented_commander:
            print(
                "[docs-check] FYI: commander endpoints present in OpenAPI but not mentioned in docs (sample):"
            )
            for p in result.undocumented_commander[:10]:
                print(f"  - {p}")

    if args.warn_only:
        return 0
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
