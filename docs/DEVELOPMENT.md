# OpenClaw Trading - 开发文档（对齐当前仓库）

> 总索引见 `docs/README.md`，运行与配置边界见 `docs/ENGINEERING.md`，运维与网络见 `docs/OPERATIONS.md`。

---

## 1. 开发基线

- Python: `3.12`（与当前 `.venv` 和生产环境一致）
- 包管理: `pip` + `requirements.txt`
- API 框架: FastAPI
- 推荐后台/值守入口: `bash scripts/start-openclaw-trading.sh`
- 推荐前台调试入口: `python -m src.main`

---

## 2. 本地开发环境

```bash
cd /home/cool/ai-trading-system
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

配置说明：

- 主业务配置：`config/config.yaml`
- 本机覆盖配置：`config/local.yaml`（可选，勿提交）
- 密钥与环境变量：`.env`

---

## 3. 启动方式（本地优先）

### 3.1 前台启动（调试推荐）

```bash
. .venv/bin/activate
python -m src.main
```

### 3.2 后台启动（值守常用）

```bash
bash scripts/start-openclaw-trading.sh
bash scripts/stop-openclaw-trading.sh
```

长期托管时不要直接把 `python -m src.main` 写进 service/supervisor 配置；统一复用启动脚本，确保 `.env` 加载、PID 镜像和日志轮转逻辑生效。

### 3.3 API-only 启动（仅接口调试）

`run_api.py` 只启动 API 服务，不覆盖完整交易主循环，适合接口层验证：

```bash
. .venv/bin/activate
python run_api.py
```

---

## 4. 最小联调检查

联调前可在 shell 中设置 **`OPENCLAW_API_BASE`**（推荐），与 `docs/API_REFERENCE.md`「API 基址、只读巡检链与 Surface」及 `GET /api/v1/modules/surface/registry` 中的 **`api_base_env`** 一致；未设置时下列示例中的主机仍默认为 `http://127.0.0.1:8000`。

```bash
curl -s http://127.0.0.1:8000/api/v1/system/health
curl -s http://127.0.0.1:8000/api/v1/s1/verify
curl -s 'http://127.0.0.1:8000/api/v1/modules/commander/snapshot?symbol=BTC/USDT'
curl -s 'http://127.0.0.1:8000/api/v1/trade/events?limit=20'
```

OpenClaw 接口最小检查：

```bash
curl -s http://127.0.0.1:8000/api/v1/modules/commander/capabilities
curl -s http://127.0.0.1:8000/api/v1/modules/commander/tool-contract
curl -s -X POST http://127.0.0.1:8000/api/v1/modules/commander/dispatch \
  -H 'Content-Type: application/json' \
  -d '{"message":"系统巡检","source":"openclaw","timeout_sec":8}'
curl -s 'http://127.0.0.1:8000/api/v1/modules/commander/dispatch/jobs/<job_id>'
```

`commander/dispatch` 最新语义（建议）：

- 同步模式默认 `timeout_sec=12`（范围 2~90），超时返回 `status=timeout`。
- 需要长耗时执行时，直接使用 `async_mode=true` 并通过 `dispatch/jobs/{job_id}` 轮询结果。
- 推荐值守脚本：`python3 scripts/commander_dispatch_client.py "系统巡检"`（同步优先，超时自动异步）。

`ai/chat` 与行情聚合调试（2026-04-20）：

- `POST /api/v1/ai/chat` 成功响应新增 `data.trace` 与 `latency_ms_total`，用于分段耗时定位：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"请简要返回当前系统状态","timeout_sec":15}'
```

- `GET /api/v1/market/state` 支持 `timeout_sec`（1.5~8.0），成功响应含 `latency_ms`，降级响应含 `timeout_sec`：

```bash
curl -s 'http://127.0.0.1:8000/api/v1/market/state?timeout_sec=3.2'
```

- `GET /api/v1/modules/ai/learning-feedback` 的 `summary` 新增观测字段：
  - `penalized_ratio`
  - `total_stop_loss_hits`
  - `penalty_rule`

---

## 5. 测试

```bash
# 建议显式设置 PYTHONPATH，避免 src 包导入差异
PYTHONPATH=/home/cool/ai-trading-system .venv/bin/pytest -q tests/e2e/test_api_surface_commander_chain.py
```

常用：

```bash
PYTHONPATH=/home/cool/ai-trading-system .venv/bin/pytest -q tests/unit
PYTHONPATH=/home/cool/ai-trading-system .venv/bin/pytest -q tests
```

---

## 6. 文档与接口一致性要求

- API 权威来源：运行时 `GET /openapi.json`
- 文档快照：`docs/API_OPENAPI_FULL.json`
- 接口语义说明：`docs/API_REFERENCE.md`

变更 API 后应至少执行：

1. 运行接口烟测（`tests/e2e/test_api_surface_commander_chain.py`）
2. 重新导出 OpenAPI 快照
3. 同步更新 `docs/API_REFERENCE.md` 中对应链路说明

建议附加执行（快速发现“文档漂移/脚本引用缺失”）：

```bash
python3 scripts/check_docs_runtime_consistency.py
# 若要对照当前代码运行时生成的 OpenAPI：
python3 scripts/check_docs_runtime_consistency.py --runtime
```

---

## 7. 常见坑（本地化迁移后）

- 不要把 `host.docker.internal` 用在裸机模式。
- 配置代理时请保持 `NO_PROXY=localhost,127.0.0.1,redis`。
- 若脚本启动失败，先检查 `.venv` 是否存在，以及 `PYTHONPATH` 是否指向仓库根目录。
