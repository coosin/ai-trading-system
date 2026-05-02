# OpenClaw Trading

智能量化交易系统（Python 3.12 + FastAPI）。

## 快速开始

1. **配置密钥**：`cp .env.example .env` 并填写交易所 / LLM 等环境变量。  
2. **主业务配置**：编辑 **`config/config.yaml`**；本机覆盖可复制 `config/config.local.example.yaml` 为 `config/local.yaml`（已在 `.gitignore` 忽略）。  
3. **本地化运行（当前推荐）**：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 全系统入口（主控 + API）
python -m src.main
# 或后台方式
bash scripts/start-openclaw-trading.sh

curl -s http://127.0.0.1:8000/api/v1/system/health
```

4. **Docker（可选）**：

```bash
docker compose build trading-system
docker compose up -d
curl -s http://127.0.0.1:8000/api/v1/system/health
```

5. **网络自检**：`python3 scripts/network_connectivity_smoke.py`  
6. **系统验收**：`bash scripts/verify_full_stack_network.sh`（成功时输出含 **`VERIFY_FULL_STACK=PASS`**）；应用快照：`curl -s http://127.0.0.1:8000/api/v1/system/acceptance`

## 运行模式说明

- **本地化模式**：直接使用仓库目录与 `.venv` 运行，避免容器网络层带来的代理与 DNS 干扰。  
- **Docker 模式**：适合隔离部署与镜像化交付。  
- 两种模式都以运行时 `GET /openapi.json` 和 `GET /api/v1/system/health` 作为可用性基准。  

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

## 说明

- 架构一页跳转：[ARCHITECTURE.md](./ARCHITECTURE.md)  
- 根目录 `DEVELOPMENT.md` 仅保留跳转至 `docs/DEVELOPMENT.md`
