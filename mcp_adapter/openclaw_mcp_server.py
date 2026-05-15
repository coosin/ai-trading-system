#!/usr/bin/env python3
"""OpenClaw MCP HTTP fallback adapter.

This lightweight adapter intentionally avoids a hard dependency on the MCP SDK.
It exposes a stable HTTP tool surface that MCP clients, CLI scripts, or local
bridges can wrap:

- GET  /health
- GET  /tools
- POST /call {"tool": "system_health", "params": {...}}
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Dict, List
from urllib.parse import urlencode

import requests
from aiohttp import web


DEFAULT_API_BASE = "http://127.0.0.1:8000"


def _tool_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", value.replace(".", "_")).strip("_").lower()
    return name or "tool"


class OpenClawMCPAdapter:
    def __init__(self, api_base: str, timeout_sec: float = 20.0) -> None:
        self.api_base = api_base.rstrip("/")
        self.timeout_sec = timeout_sec

    def _url(self, path: str, params: Dict[str, Any] | None = None) -> str:
        url = f"{self.api_base}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url = f"{url}?{urlencode(clean, doseq=True)}"
        return url

    def _get_json(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        resp = requests.get(self._url(path, params), timeout=self.timeout_sec)
        resp.raise_for_status()
        return resp.json()

    def manifest(self) -> Dict[str, Any]:
        try:
            data = self._get_json("/api/v1/modules/surface/mcp-manifest")
            payload = data.get("data") if isinstance(data, dict) else None
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return self._fallback_manifest()

    def _fallback_manifest(self) -> Dict[str, Any]:
        surface = self._get_json("/api/v1/surface/registry")
        routes = ((surface.get("data") or {}).get("routes") or []) if isinstance(surface, dict) else []
        read_tools: List[Dict[str, Any]] = []
        for route in routes:
            if route.get("method") != "GET":
                continue
            read_tools.append(
                {
                    "name": _tool_name(str(route.get("capability") or route.get("path"))),
                    "capability": route.get("capability"),
                    "method": route.get("method"),
                    "path": route.get("path"),
                    "domain": route.get("domain"),
                    "description": route.get("summary"),
                    "safety": "read_only",
                }
            )
        return {
            "contract_version": "fallback",
            "protocol": "openclaw-mcp-http-fallback",
            "defaults": {"mode": "read_only", "timeout_sec": self.timeout_sec},
            "read_tools": read_tools,
            "guarded_write_tools": [],
            "tool_count": {"read": len(read_tools), "guarded_write": 0},
        }

    def tools(self) -> List[Dict[str, Any]]:
        manifest = self.manifest()
        return list(manifest.get("read_tools") or [])

    def call(self, tool_name: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        params = params or {}
        tools = {str(t.get("name")): t for t in self.tools()}
        tool = tools.get(tool_name)
        if not tool:
            raise web.HTTPNotFound(text=json.dumps({"success": False, "message": f"unknown tool: {tool_name}"}))
        if tool.get("method") != "GET":
            raise web.HTTPForbidden(text=json.dumps({"success": False, "message": "only read-only GET tools are callable"}))
        path = str(tool.get("path") or "")
        if "{" in path or "}" in path:
            for key, value in params.items():
                path = path.replace("{" + str(key) + "}", str(value))
            if "{" in path or "}" in path:
                raise web.HTTPBadRequest(text=json.dumps({"success": False, "message": "missing path parameter"}))
        query = {k: v for k, v in params.items() if "{" + str(k) + "}" not in str(tool.get("path") or "")}
        return self._get_json(path, query)


def create_app(adapter: OpenClawMCPAdapter) -> web.Application:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        try:
            payload = adapter._get_json("/api/v1/system/health")
            ok = bool(payload.get("success"))
            status = (payload.get("data") or {}).get("status")
        except Exception as exc:
            return web.json_response({"success": False, "api_base": adapter.api_base, "error": str(exc)}, status=503)
        return web.json_response({"success": ok, "api_base": adapter.api_base, "system_status": status})

    async def manifest(_: web.Request) -> web.Response:
        return web.json_response({"success": True, "data": adapter.manifest()})

    async def tools(_: web.Request) -> web.Response:
        return web.json_response({"success": True, "tools": adapter.tools()})

    async def call(request: web.Request) -> web.Response:
        body = await request.json()
        tool = str(body.get("tool") or body.get("name") or "").strip()
        params = body.get("params") if isinstance(body.get("params"), dict) else {}
        if not tool:
            return web.json_response({"success": False, "message": "tool is required"}, status=400)
        try:
            return web.json_response({"success": True, "tool": tool, "result": adapter.call(tool, params)})
        except web.HTTPException:
            raise
        except Exception as exc:
            return web.json_response({"success": False, "tool": tool, "message": str(exc)}, status=502)

    app.router.add_get("/health", health)
    app.router.add_get("/manifest", manifest)
    app.router.add_get("/tools", tools)
    app.router.add_post("/call", call)
    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="http", choices=["http"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=18888, type=int)
    parser.add_argument("--api-base", default=os.environ.get("OPENCLAW_API_BASE") or DEFAULT_API_BASE)
    parser.add_argument("--timeout-sec", default=20.0, type=float)
    args = parser.parse_args()
    adapter = OpenClawMCPAdapter(api_base=args.api_base, timeout_sec=args.timeout_sec)
    web.run_app(create_app(adapter), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
