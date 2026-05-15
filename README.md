# OpenClaw Trading

智能量化交易系统（Python 3.12 + FastAPI）。

## 快速开始

1. **配置密钥**：`cp .env.example .env` 并填写交易所 / LLM 等环境变量。  
2. **主业务配置**：编辑 **`config/config.yaml`**；本机覆盖可复制 `config/config.local.example.yaml` 为 `config/local.yaml`（已在 `.gitignore` 忽略）。  
3. **本地化运行**：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 全系统生产入口（主控 + API）
bash scripts/start-openclaw-trading.sh
bash scripts/stop-openclaw-trading.sh

# 前台调试入口
python -m src.main

curl -s http://127.0.0.1:8000/api/v1/system/health
```

生产托管建议统一使用 `scripts/start-openclaw-trading.sh`，或调用同一脚本的 systemd 模板 [deploy/systemd/openclaw-trading.service](/home/cool/ai-trading-system/deploy/systemd/openclaw-trading.service)。不要再直接把 `python -m src.main` 写进长期托管入口，否则会绕过 `.env` 加载、PID 记账和启动期日志轮转。

标准 systemd 托管建议同时安装主服务与 health suite timers：

```bash
sudo cp deploy/systemd/openclaw-trading.service /etc/systemd/system/
sudo cp deploy/systemd/openclaw-health-audit.service /etc/systemd/system/
sudo cp deploy/systemd/openclaw-health-audit.timer /etc/systemd/system/
sudo cp deploy/systemd/openclaw-live-stability-monitor.service /etc/systemd/system/
sudo cp deploy/systemd/openclaw-live-stability-monitor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-trading.service
sudo systemctl enable --now openclaw-health-audit.timer
sudo systemctl enable --now openclaw-live-stability-monitor.timer
```

快速检查：

```bash
systemctl status openclaw-trading.service --no-pager
systemctl list-timers --all 'openclaw-*' --no-pager
sed -n '1,120p' logs/health/health_suite_summary.md
```

脚本或外部系统对接时，建议在 `.env` 中设置 **`OPENCLAW_API_BASE=http://127.0.0.1:8000`**（或与反代一致的 URL），与 `GET /api/v1/modules/surface/registry` 返回的 **`api_base_env`** 及 **`docs/API_REFERENCE.md`** 说明一致。

4. **网络自检**：`python3 scripts/network_connectivity_smoke.py`（可选 `OPENCLAW_API_BASE=... python3 scripts/network_connectivity_smoke.py --include-api` 顺带探活本机 API）  
5. **系统验收**（需 API 已在本机监听）：`bash scripts/verify_full_stack_network.sh`（成功时输出含 **`VERIFY_FULL_STACK=PASS`**）；应用快照：`curl -s http://127.0.0.1:8000/api/v1/system/acceptance`

## 运行模式说明

- **本地化模式**：直接使用仓库目录与 `.venv` 运行；以运行时 `GET /openapi.json` 和 `GET /api/v1/system/health` 作为可用性基准。  

## 统一开仓/仓位入口（强烈推荐）

所有“单币种最大开仓额度 / 同向持仓上限 / 双向对冲上限”的设置，统一在 **`config/config.yaml` → `trading.position_limits`**：

- **`symbol_max_margin_ratio`**: 单币种最大开仓保证金占用（占 **available** 比例），默认 `0.2`（20%）
- **`max_same_direction_positions`**: 同向持仓数上限（long/short 分别计数），默认 `5`
- **`max_positions_oneway`**: 单向模式（oneway）下总持仓上限，默认 `5`
- **`max_positions_hedge`**: 双向对冲并存（long+short 同时存在）时总持仓上限，默认 `8`
- **`hard_max_positions`**: 最终硬上限（任何路径都不得超过），默认 `8`
- **`scale_in_min_confidence_2/3/4`**: 第2/3/4笔同向加仓的最小置信度门槛（默认 `0.77/0.82/0.87`）

运行期可通过 `GET /api/v1/modules/commander/trading-diagnosis` 查看 `position_limits_snapshot` 确认是否生效。

## 文档

**正式文档索引**：[docs/README.md](./docs/README.md)（工程总览 **[docs/ENGINEERING.md](./docs/ENGINEERING.md)**、运维 **[docs/OPERATIONS.md](./docs/OPERATIONS.md)**、MCP 基线 **[docs/MCP_BASELINE.md](./docs/MCP_BASELINE.md)**、OpenClaw 对接 **[docs/OPENCLAW_INTEGRATION_GUIDE.md](./docs/OPENCLAW_INTEGRATION_GUIDE.md)**）。

**AI 维护交接（2026 Q2 优化与验证）**：[docs/AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md](./docs/AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md) — 测试结论、环境变量、验收命令与调参流程的单一入口。

## 交易所实时同步与“真值记账”（2026-05 更新）

为确保**钱包/持仓/成交数据与交易所实时一致**，系统已收敛为“自动同步 + 真值回填 + 分账账本”的默认行为：

- **全自动同步线程**：启动后自动周期同步余额/持仓，并自动回填近期平仓记录的真实 `pnl/fee/均价`
- **事实账本（与 app.log 分离）**：`logs/exchange_sync/exchange_truth.jsonl`（JSON Lines，仅追加）
- **对账接口**：`GET /api/v1/trades/reconcile`、`GET /api/v1/trades/reconcile/report`

详见：

- 运维：[`docs/OPERATIONS.md`](./docs/OPERATIONS.md)
- API：[`docs/API_REFERENCE.md`](./docs/API_REFERENCE.md)
- 排障：[`docs/TRADING_DEBUG_PLAYBOOK.md`](./docs/TRADING_DEBUG_PLAYBOOK.md)

## 说明

- 架构一页跳转：[ARCHITECTURE.md](./ARCHITECTURE.md)  
- 根目录 `DEVELOPMENT.md` 仅保留跳转至 `docs/DEVELOPMENT.md`
