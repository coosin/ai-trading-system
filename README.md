# OpenClaw Trading

OpenClaw Trading 是一个 Python 3.12 + FastAPI 的智能量化交易系统。当前架构以标准域 API、AI 决策、ExecutionGateway 单写执行脊柱、风险门控、交易后验和学习闭环为核心。

## 快速启动

```bash
cd /home/cool/ai-trading-system
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

bash scripts/start-openclaw-trading.sh
curl -s http://127.0.0.1:8000/api/v1/system/health
```

前台调试可用：

```bash
python -m src.main
```

长期托管不要直接把 `python -m src.main` 写进 service。生产建议使用 `deploy/systemd/openclaw-trading.service`，它会调用同一套启动/停止脚本，保留 `.env` 加载、PID 记账和日志轮转。

## 当前系统入口

- API 基址：`OPENCLAW_API_BASE`，默认 `http://127.0.0.1:8000`。
- 标准接口：`/api/v1/{domain}/...`。
- 接口发现：`GET /api/v1/surface/registry`。
- 兼容能力面：`GET /api/v1/modules/surface/registry`。
- OpenAPI：`GET /openapi.json` 或浏览器访问 `/docs`。

最小巡检：

```bash
OPENCLAW_API_BASE=${OPENCLAW_API_BASE:-http://127.0.0.1:8000}
curl -s "$OPENCLAW_API_BASE/api/v1/system/health"
curl -s "$OPENCLAW_API_BASE/api/v1/system/status"
curl -s "$OPENCLAW_API_BASE/api/v1/s1/verify"
curl -s "$OPENCLAW_API_BASE/api/v1/commander/system-mastery?symbol=BTC/USDT"
```

## 配置

- 主业务配置：`config/config.yaml`。
- 本机覆盖：`config/local.yaml`，不要提交。
- 密钥与本机环境：`.env`。
- 环境变量覆盖 YAML：`OPENCLAW__section__key__nested=value`。

当前交易关键门控：

- `trading.position_limits.symbol_max_margin_ratio=0.2`。
- 同向 slot 上限：`max_same_direction_positions=5`。
- 总仓位上限：`max_positions_oneway=5`、`max_positions_hedge=8`、`hard_max_positions=8`。
- 第 1-5 笔开仓/加仓置信度：`0.72 / 0.77 / 0.82 / 0.87 / 0.92`。
- 满仓替弱置信度：`ai_brain.policy.replace_worst_min_confidence=0.95`。
- 单写者：`ai_brain.single_write_owner=ai_core`。

## 文档

正式文档入口：[docs/README.md](./docs/README.md)。

重点文档：

- [docs/STANDARD_DOMAIN_ARCHITECTURE.md](./docs/STANDARD_DOMAIN_ARCHITECTURE.md)
- [docs/API_REFERENCE.md](./docs/API_REFERENCE.md)
- [docs/OPERATIONS.md](./docs/OPERATIONS.md)
- [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md)
- [docs/OPENCLAW_INTEGRATION_GUIDE.md](./docs/OPENCLAW_INTEGRATION_GUIDE.md)
- [docs/MCP_BASELINE.md](./docs/MCP_BASELINE.md)

