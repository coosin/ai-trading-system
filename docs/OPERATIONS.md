# OpenClaw 运维手册

本文聚焦部署、网络、巡检和排障。工程结构见 [ENGINEERING.md](./ENGINEERING.md)，API 见 [API_REFERENCE.md](./API_REFERENCE.md)。

## 运行模式

当前生产路径是裸机运行：

- 工作目录：`/home/cool/ai-trading-system`。
- Python 环境：项目内 `.venv`。
- 启动脚本：`scripts/start-openclaw-trading.sh`。
- 停止脚本：`scripts/stop-openclaw-trading.sh`。
- systemd 模板：`deploy/systemd/openclaw-trading.service`。
- API 默认监听：`0.0.0.0:8000`，本机访问 `http://127.0.0.1:8000`。

不要在长期托管中直接执行 `python -m src.main`，否则会绕过 `.env`、PID 和日志轮转逻辑。

## 首次部署

```bash
cd /home/cool/ai-trading-system
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
bash scripts/start-openclaw-trading.sh
```

设置基址：

```bash
export OPENCLAW_API_BASE=http://127.0.0.1:8000
```

## systemd 托管

```bash
sudo cp deploy/systemd/openclaw-trading.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-trading.service
systemctl status openclaw-trading.service --no-pager
```

当前 service 要点：

- `Type=forking`。
- `WorkingDirectory=/home/cool/ai-trading-system`。
- `EnvironmentFile=-/home/cool/ai-trading-system/.env`。
- `ExecStart=/home/cool/ai-trading-system/scripts/start-openclaw-trading.sh`。
- `ExecStop=/home/cool/ai-trading-system/scripts/stop-openclaw-trading.sh`。
- `PIDFile=/home/cool/ai-trading-system/runtime/openclaw-trading.pid`。

如安装健康审计 timer：

```bash
sudo cp deploy/systemd/openclaw-health-audit.service /etc/systemd/system/
sudo cp deploy/systemd/openclaw-health-audit.timer /etc/systemd/system/
sudo cp deploy/systemd/openclaw-live-stability-monitor.service /etc/systemd/system/
sudo cp deploy/systemd/openclaw-live-stability-monitor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-health-audit.timer
sudo systemctl enable --now openclaw-live-stability-monitor.timer
```

## 最小巡检

```bash
OPENCLAW_API_BASE=${OPENCLAW_API_BASE:-http://127.0.0.1:8000}
curl -s "$OPENCLAW_API_BASE/api/v1/system/health"
curl -s "$OPENCLAW_API_BASE/api/v1/system/status"
curl -s "$OPENCLAW_API_BASE/api/v1/s1/verify"
curl -s "$OPENCLAW_API_BASE/api/v1/surface/registry"
curl -s "$OPENCLAW_API_BASE/api/v1/commander/system-mastery?symbol=BTC/USDT"
```

进一步定位：

```bash
curl -s "$OPENCLAW_API_BASE/api/v1/account/snapshot"
curl -s "$OPENCLAW_API_BASE/api/v1/execution/spine"
curl -s "$OPENCLAW_API_BASE/api/v1/trades/lifecycle"
curl -s "$OPENCLAW_API_BASE/api/v1/strategy/overview"
```

## 网络与代理

推荐 `.env` 中保持：

```bash
NO_PROXY=localhost,127.0.0.1,redis
OPENCLAW_HTTP_PROXY=http://127.0.0.1:7890
OPENCLAW_HTTPS_PROXY=http://127.0.0.1:7890
OPENCLAW_OKX_HTTP_PROXY=http://127.0.0.1:7890
OPENCLAW_OKX_HTTPS_PROXY=http://127.0.0.1:7890
OPENCLAW_OKX_PROXY_ONLY=1
```

当前 OKX 推荐经本机 `mihomo` mixed-port `7890`，`okx.com` / `okx.cab` 由 OKX 专用分组分流。旧本地 GCP 隧道 `127.0.0.1:17892/17893` 不应作为主链路。

当前运行补充：

- `OPENCLAW_OKX_WS_ENABLED=1`，公共 tickers 由 WS 分担，降低 REST 压力。
- 若宿主机代理出口对 OKX 公共 WS 不稳定，系统会按指数退避重连；连续短连达到阈值后，公共 WS 会暂停 `300s` 再试。
- `OPENCLAW_OKX_PROXY_ONLY=1` 仍保持开启，说明当前生产假设是“OKX 必须经代理出口”；如要切直连，先在宿主机完成连通性验证，不要直接在线上切。

检查：

```bash
curl -s http://127.0.0.1:9090/proxies/OKX
curl -s "$OPENCLAW_API_BASE/api/v1/system/health"
python3 scripts/network_connectivity_smoke.py --include-api
```

## LLM 当前基线

当前生产基线不再让交易系统直接绑定真实模型名，而是统一走宿主机 `CLIProxyAPI`：

- `base_url=http://127.0.0.1:8317/v1`
- 交易逻辑别名：
  - `trading-fast`
  - `trading-json`
  - `trading-reasoning`
  - `trading-fallback`
- 当前 `ai_trading.ai_config.model_id=trading-reasoning`

含义：

- 交易系统只选择逻辑槽位，不直接依赖上游真实模型名。
- `CLIProxyAPI` 负责把逻辑槽位映射到当前真实可用模型。
- 诊断面若再出现历史真实模型名，优先怀疑文档或配置漂移，而不是先怀疑交易主链已经切回旧模型。

检查：

```bash
curl -s "$OPENCLAW_API_BASE/api/v1/ai-models/default"
curl -s "$OPENCLAW_API_BASE/api/v1/modules/commander/trading-diagnosis?limit_events=20&timeout_sec=10"
python3 scripts/validate_trading_model_aliases.py
rg -n "127.0.0.1:8317|trading-reasoning|trading-fast|trading-json|trading-fallback" logs/app.log
```

## 配置重载

修改 `config/config.yaml`、`.env` 或 `src/` 后，重启主进程：

```bash
sudo systemctl restart openclaw-trading.service
# 或
bash scripts/stop-openclaw-trading.sh
bash scripts/start-openclaw-trading.sh
```

## 交易执行与仓位门控

运维排查交易问题时先确认：

- `ai_brain.single_write_owner=ai_core`。
- `trading.position_limits` 是否符合预期。
- ExecutionGateway 是否拒单，查看 `/api/v1/execution/spine` 和 `/api/v1/trades/lifecycle`。
- 第 1-5 笔开仓置信度门槛为 `0.72 / 0.77 / 0.82 / 0.87 / 0.92`。
- 满仓替弱需要 `replace_worst_min_confidence=0.95`。

## 日志与事实账本

- 主日志：`logs/app.log`。
- 启动脚本输出：`logs/nohup.out` 或脚本配置的轮转文件。
- 交易所事实账本：`logs/exchange_sync/exchange_truth.jsonl`。
- 健康审计摘要：`logs/health/health_suite_summary.md`。

排障顺序：

```bash
tail -n 120 logs/app.log
tail -n 50 logs/exchange_sync/exchange_truth.jsonl
systemctl status openclaw-trading.service --no-pager
```

## 上线验收

```bash
python3 scripts/check_docs_runtime_consistency.py
pytest -q tests/unit/test_standard_domain_api.py tests/e2e/test_api_surface_commander_chain.py
bash scripts/verify_full_stack_network.sh
```

`verify_full_stack_network.sh` 成功时应输出 `VERIFY_FULL_STACK=PASS`。
