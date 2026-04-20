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

curl -s http://127.0.0.1:8000/health
```

4. **Docker（可选）**：

```bash
docker compose build trading-system
docker compose up -d
curl -s http://127.0.0.1:8000/health
```

5. **网络自检**：`python3 scripts/network_connectivity_smoke.py`  
6. **系统验收**：`bash scripts/verify_full_stack_network.sh`（成功时输出含 **`VERIFY_FULL_STACK=PASS`**）；应用快照：`curl -s http://127.0.0.1:8000/api/v1/system/acceptance`

## 运行模式说明

- **本地化模式**：直接使用仓库目录与 `.venv` 运行，避免容器网络层带来的代理与 DNS 干扰。  
- **Docker 模式**：适合隔离部署与镜像化交付。  
- 两种模式都以运行时 `GET /openapi.json` 和 `GET /health` 作为可用性基准。  

## 文档

**正式文档索引**：[docs/README.md](./docs/README.md)（工程总览 **[docs/ENGINEERING.md](./docs/ENGINEERING.md)**、运维 **[docs/OPERATIONS.md](./docs/OPERATIONS.md)**、MCP 基线 **[docs/MCP_BASELINE.md](./docs/MCP_BASELINE.md)**、OpenClaw 对接 **[docs/OPENCLAW_INTEGRATION_GUIDE.md](./docs/OPENCLAW_INTEGRATION_GUIDE.md)**）。

## 说明

- 架构一页跳转：[ARCHITECTURE.md](./ARCHITECTURE.md)  
- 根目录 `DEVELOPMENT.md` 仅保留跳转至 `docs/DEVELOPMENT.md`
