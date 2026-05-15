# OpenClaw 对接与验收指南

本文说明如何将 **OpenClaw 交易 API** 作为控制面接入：配置、关键只读接口、巡检脚本与上线核对顺序。更细的运维与网络见 **[OPERATIONS.md](./OPERATIONS.md)**；MCP 关系与基线见 **[MCP_BASELINE.md](./MCP_BASELINE.md)**；全量路由说明见 **[API_REFERENCE.md](./API_REFERENCE.md)**。

---

## 1. 配置

- **主配置（必存于仓库）**：`config/config.yaml`。
- **本机覆盖（勿提交）**：将 `config/config.local.example.yaml` 复制为同目录 **`config/local.yaml`**（或 `local.yml` / `local.json`），填写密钥与覆盖项。详见 **[DEVELOPMENT.md](./DEVELOPMENT.md)**、`config/config.yaml` 顶部注释。

---

## 2. 控制面只读探针（上线前建议）

服务监听默认 `http://127.0.0.1:8000`（可按部署修改主机与端口）。

```bash
curl -s http://127.0.0.1:8000/api/v1/modules/commander/capabilities
curl -s http://127.0.0.1:8000/api/v1/modules/commander/tool-contract
curl -s http://127.0.0.1:8000/api/v1/modules/surface/channels
curl -s http://127.0.0.1:8000/api/v1/modules/surface/registry
curl -s 'http://127.0.0.1:8000/api/v1/modules/commander/snapshot?symbol=BTC/USDT'
```

**交易闭环一页式摘要**（决策 trace、执行网关、对账、监控等聚合，便于运行中优化排查；非纯历史报表）：

- 路径：`/api/v1/modules/commander/closed-loop-summary`（GET，可选查询参数 `trace_limit`，默认 120）

```bash
curl -s 'http://127.0.0.1:8000/api/v1/modules/commander/closed-loop-summary?trace_limit=120'
```

运行中建议至少补两类只读探针，不要只接健康接口：

- `GET /api/v1/modules/commander/trading-diagnosis`
  - 重点读取 `data.signal_and_guard.workflow_focus`
  - 用于判断系统当前主要卡在 `analysis / guard / execution / reconciliation` 的哪一段
- `GET /api/v1/modules/commander/decision-traces`
  - 重点读取 `top_workflow_stages` / `top_workflow_statuses` / `top_reconciliation_blocks`
  - 用于验证聚合卡点是否与总诊断一致

如果你的外部控制面、值守机器人或 dashboard 只拉健康状态，不拉这两类 workflow 语义，排障时仍然会退回“系统活着但不知道为什么不交易”的旧状态。

可选写入探针（高峰期若 HTTP 超时，可用仓库脚本代替）：

```bash
python3 scripts/commander_dispatch_client.py "系统巡检" --source openclaw
```

---

## 3. 健康与稳定性脚本

| 脚本 | 用途 |
|------|------|
| `scripts/health_check.sh` | API 健康 JSON + Redis 可用性（环境变量见脚本内注释） |
| `scripts/prod_stability_check.py` | 生产级稳定性一票验收（健康、交易所、绑定、对账等） |
| `scripts/trading_exec_fullcheck.py` | 交易执行链路与诊断摘要 |
| `scripts/verify.py` | 统一入口：`trading` / `network` / `trading-gates` |

示例：

```bash
bash scripts/health_check.sh
python3 scripts/prod_stability_check.py
python3 scripts/verify.py trading-gates
```

---

## 4. 网络出站

部署后确认容器/宿主机可访问交易所与依赖服务：

```bash
python3 scripts/network_connectivity_smoke.py
python3 scripts/production_network_baseline.py --check-only
```

详见 **OPERATIONS.md** 第 3 节（代理、OKX、`NO_PROXY` 等）。

---

## 5. OpenAPI 与文档一致性

本地可运行（不依赖服务进程）：

```bash
python3 scripts/check_docs_runtime_consistency.py
python3 scripts/check_docs_runtime_consistency.py --runtime
```

完整 OpenAPI 快照位于 **`docs/API_OPENAPI_FULL.json`**（可由当前代码生成，供文档检查与外部工具导入）。
