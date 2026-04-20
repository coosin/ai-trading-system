#!/usr/bin/env bash
# 本地化：代理出网、本机 AIClient、OKX 公网、合并配置中的代理 URL 自检。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 供内联 Python 读取密钥（不依赖 python-dotenv）
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source ./.env
  set +a
fi

# 与 config 合并后注入一致：默认本机 mixed-port；可用环境变量覆盖
PROXY_URL="${OPENCLAW_HTTP_PROXY:-${HTTP_PROXY:-http://127.0.0.1:7890}}"
export HTTP_PROXY="${HTTP_PROXY:-$PROXY_URL}"
export HTTPS_PROXY="${HTTPS_PROXY:-$PROXY_URL}"

echo "== 1) 代理出网（经 $HTTP_PROXY）→ OKX 公共时间 API =="
code="$(curl -sS -o /tmp/okx_time.json -w '%{http_code}' -m 15 -x "$HTTP_PROXY" "https://www.okx.com/api/v5/public/time" || true)"
echo "HTTP $code"
head -c 300 /tmp/okx_time.json 2>/dev/null || true
echo ""

echo "== 2) 本机 AIClient（直连，不走代理）→ :3000 =="
curl -sS -m 5 "http://127.0.0.1:3000/" 2>/dev/null | head -c 400 || echo "(无响应: 请确认 aiclient2api 在本机 3000 监听)"

echo ""
echo "== 3) 合并配置中的 proxy URL（仅 YAML + 与运行时相同的 URL 构造，避免拉全量依赖）==="
python3 <<PY
from pathlib import Path
import importlib.util
import sys

try:
    import yaml  # type: ignore
except ImportError:
    print("SKIP: 需要 PyYAML（pip install pyyaml）")
    sys.exit(0)

root_dir = Path("${ROOT}")

def deep_merge(base, upd):
    for k, v in (upd or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base

def load_yaml(p: Path):
    if not p.is_file():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

root = load_yaml(root_dir / "config" / "config.yaml")
deep_merge(root, load_yaml(root_dir / "config" / "local.yaml"))
px = root.get("proxy") or {}
nev_path = root_dir / "src" / "modules" / "core" / "network_env_from_config.py"
spec = importlib.util.spec_from_file_location("openclaw_network_env", nev_path)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore[union-attr]
print("build_proxy_url_from_config:", mod.build_proxy_url_from_config(px))
llm = root.get("llm") or {}
models = llm.get("models") or []
if models:
    print("llm.models[0].base_url:", models[0].get("base_url"))
PY

echo ""
echo "== 4) LLM 最小请求（curl → 本机 AIClient OpenAI 兼容端点，不依赖项目 venv）==="
if [[ -z "${AICLIENT_API_KEY:-}" ]]; then
  echo "SKIP: 未设置 AICLIENT_API_KEY"
else
  curl -sS -m 60 "http://127.0.0.1:3000/gemini-cli-oauth/v1/chat/completions" \
    -H "Authorization: Bearer ${AICLIENT_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"model":"gemini-2.5-flash","messages":[{"role":"user","content":"Reply with exactly: pong"}],"max_tokens":16}' \
    | head -c 500
  echo ""
fi

echo ""
echo "完成。若 (1) 失败：检查 Mihomo/Clash 是否在 ${HTTP_PROXY#http://} 监听；若 (4) 失败：检查 AICLIENT_API_KEY 与 127.0.0.1:3000。"
