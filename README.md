# OpenClaw Trading

智能量化交易系统（Python 3.12 + FastAPI）。

## 快速开始

1. **配置密钥**：`cp .env.example .env` 并填写交易所 / LLM 等环境变量。  
2. **主业务配置**：编辑 **`config/config.yaml`**；本机覆盖可复制 `config/config.local.example.yaml` 为 `config/local.yaml`（已在 `.gitignore` 忽略）。  
3. **Docker（推荐）**：

```bash
docker compose build trading-system
docker compose up -d
curl -s http://127.0.0.1:8000/health
```

4. **网络自检**：`python3 scripts/network_connectivity_smoke.py`  
5. **全栈验收（Docker 已起）**：`bash scripts/verify_full_stack_network.sh`（成功时输出含 **`VERIFY_FULL_STACK=PASS`**）；应用快照：`curl -s http://127.0.0.1:8000/api/v1/system/acceptance`

## 文档

**正式文档索引**：[docs/README.md](./docs/README.md)（工程总览 **[docs/ENGINEERING.md](./docs/ENGINEERING.md)**、运维 **[docs/OPERATIONS.md](./docs/OPERATIONS.md)**）。

## 说明

- 架构一页跳转：[ARCHITECTURE.md](./ARCHITECTURE.md)  
- 根目录 `DEVELOPMENT.md` 仅保留跳转至 `docs/DEVELOPMENT.md`
