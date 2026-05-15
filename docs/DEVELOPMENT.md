# OpenClaw 开发文档

本文对齐当前仓库开发方式。架构见 [ENGINEERING.md](./ENGINEERING.md)，接口边界见 [STANDARD_DOMAIN_ARCHITECTURE.md](./STANDARD_DOMAIN_ARCHITECTURE.md)，运维见 [OPERATIONS.md](./OPERATIONS.md)。

## 开发基线

- Python：`3.12`。
- 包管理：`pip` + `requirements.txt`。
- API 框架：FastAPI。
- 生产/值守入口：`bash scripts/start-openclaw-trading.sh`。
- 前台调试入口：`python -m src.main`。
- API-only 调试入口：`python run_api.py`。

## 本地环境

```bash
cd /home/cool/ai-trading-system
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

配置文件：

- `config/config.yaml`：主业务配置，必须随仓库维护。
- `config/local.yaml`：本机覆盖，勿提交。
- `.env`：密钥、代理、本机运行环境。
- `OPENCLAW__section__key__nested=value`：环境变量覆盖 YAML。

## 启动

```bash
# 前台调试
python -m src.main

# 后台值守
bash scripts/start-openclaw-trading.sh
bash scripts/stop-openclaw-trading.sh

# API-only
python run_api.py
```

长期托管统一复用 `scripts/start-openclaw-trading.sh`，不要让 service 直接执行 `python -m src.main`。

## 最小联调

```bash
OPENCLAW_API_BASE=${OPENCLAW_API_BASE:-http://127.0.0.1:8000}
curl -s "$OPENCLAW_API_BASE/api/v1/system/health"
curl -s "$OPENCLAW_API_BASE/api/v1/surface/registry"
curl -s "$OPENCLAW_API_BASE/api/v1/s1/verify"
curl -s "$OPENCLAW_API_BASE/api/v1/commander/system-mastery?symbol=BTC/USDT"
curl -s "$OPENCLAW_API_BASE/api/v1/trades/lifecycle"
```

兼容能力面检查：

```bash
curl -s "$OPENCLAW_API_BASE/api/v1/modules/surface/registry"
curl -s "$OPENCLAW_API_BASE/api/v1/modules/commander/capabilities"
curl -s "$OPENCLAW_API_BASE/api/v1/modules/commander/tool-contract"
```

## 测试

常用快速测试：

```bash
PYTHONPATH=/home/cool/ai-trading-system pytest -q tests/unit/test_standard_domain_api.py
PYTHONPATH=/home/cool/ai-trading-system pytest -q tests/e2e/test_api_surface_commander_chain.py
PYTHONPATH=/home/cool/ai-trading-system pytest -q tests/unit/test_execution_gateway.py tests/test_ai_trading_engine.py
```

全量测试：

```bash
PYTHONPATH=/home/cool/ai-trading-system pytest -q tests
```

## API 变更规则

新增公共能力必须同步修改：

- `src/modules/<domain>/api` 模块：实际路由。
- `src/modules/<domain>/service.py` 或对应 domain service：业务逻辑。
- `src/modules/api/standard_registry.py`：唯一 capability 注册。
- `src/modules/api/route_catalog.py`：如属于巡检链或常用只读路由，需要更新。
- `docs/API_REFERENCE.md` 和 `docs/STANDARD_DOMAIN_ARCHITECTURE.md`。
- 测试：至少覆盖 `tests/unit/test_standard_domain_api.py` 或相关 domain 测试。

不要把新增公共能力只挂在 modules v1 前缀下。

## 文档一致性

```bash
python3 scripts/check_docs_runtime_consistency.py
```

如果文档引用了不存在的端点或文件，脚本会返回非零。运行时 OpenAPI 权威来源是 `/openapi.json`。

## 常见坑

- 裸机模式不要使用 `host.docker.internal`。
- 代理环境保持 `NO_PROXY=localhost,127.0.0.1,redis`。
- OKX 独立代理变量优先检查 `.env`：`OPENCLAW_OKX_HTTP_PROXY`、`OPENCLAW_OKX_HTTPS_PROXY`、`OPENCLAW_OKX_PROXY_ONLY`。
- 不要绕过 `ExecutionGateway` 直接交易所下单。
- 不要在 API 层堆业务逻辑；跨域聚合放 `commander`。
