# OpenClaw Trading — 运维手册

与 [ENGINEERING.md](./ENGINEERING.md) 配合使用：本节聚焦**部署、网络、巡检与排障**。

---

## 0. 运行模式选择（先确认）

当前系统以**裸机运行**为主。若延续旧容器化参数到裸机场景，最常见冲突是代理地址与回环地址。

- **裸机模式**（默认）：
  - 建议从项目根运行：`bash scripts/start-openclaw-trading.sh`（长期托管优先）或 `python3 run_api.py`（前台/临时）；systemd 应复用同一启动脚本，避免绕过 `.env`、PID 与日志轮转
  - 对外基址统一为：`http://127.0.0.1:8000`（本机）或实际监听地址；**脚本与巡检**建议在 `.env` 或 shell 中设置 **`OPENCLAW_API_BASE`**（优先于历史变量 `ACCEPTANCE_BASE`、`BASE_URL`），与 `src/utils/openclaw_api_client.py` 及 `GET /api/v1/modules/surface/registry` 返回的 **`api_base_env`** 对齐。
  - 若配置了代理，请确认 `NO_PROXY=127.0.0.1,localhost,redis`
  - 禁止把 `host.docker.internal` 写入裸机代理/上游地址

裸机最小健康检查：

```bash
curl -s http://127.0.0.1:8000/api/v1/system/health
curl -s http://127.0.0.1:8000/api/v1/s1/verify
curl -s 'http://127.0.0.1:8000/api/v1/modules/commander/audit?enrich=true'
curl -s http://127.0.0.1:8000/api/v1/auth/status
```

本页后续所有 `curl` 示例可统一替换为：

```bash
OPENCLAW_API_BASE=${OPENCLAW_API_BASE:-http://127.0.0.1:8000}
curl -s "$OPENCLAW_API_BASE/api/v1/system/health"
# 兼容：未设置 OPENCLAW_API_BASE 时仍可使用 BASE_URL
# BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
```

只读巡检的**推荐顺序**以运行中 **`GET .../modules/surface/registry`** 的 **`read_pipeline`** 字段为准（与 `src/modules/api/route_catalog.py` 同源）。

## 0.0 LLM 主模型现状（2026-05-12 起）

当前生产主模型已切换为 **讯飞 Astron Code Latest**（OpenAI 兼容）：

- `model_id`: `astron-code-latest`
- `base_url`: `https://maas-coding-api.cn-huabei-1.xf-yun.com/v2`
- `api_key_env`: `XFYUN_ASTRON_API_KEY`

最小检查：

```bash
curl -s http://127.0.0.1:8000/api/v1/ai-models/default
rg -n "astron-code-latest|maas-coding-api.cn-huabei-1.xf-yun.com" logs/app.log
```

判读重点：

- 若默认模型仍不是 `astron-code-latest`
  - 说明交易进程尚未重启或未重新加载模型配置
- 若日志持续出现 `https://api.deepseek.com/v1/chat/completions` 与 `402 Payment Required`
  - 说明旧 DeepSeek 路径仍在运行，需确认当前进程是否已切换到新配置
- 若进程内最小调用返回 `success=true`
  - 即可认定 Astron 主模型链路已恢复

## 0.1 OKX 专线拓扑（2026-05-12 更新）

当前运行建议将 **OKX** 与 **其他第三方流量** 分开看：

- **普通第三方流量**
  - 应用全局代理：`http://127.0.0.1:7890`
  - 典型对象：LLM、新闻、Reddit、部分外部数据源

- **OKX 专用流量**
  - 应用内 OKX 独立代理变量：
    - `OPENCLAW_OKX_HTTP_PROXY=http://127.0.0.1:7890`
    - `OPENCLAW_OKX_HTTPS_PROXY=http://127.0.0.1:7890`
    - `OPENCLAW_OKX_PROXY_ONLY=1`
  - `mihomo` 对 `okx.com` / `okx.cab` 走独立 `OKX` 分组
  - 当前推荐优先级：
    - `AUTO -> DIRECT`
  - 说明：
    - 旧 GCP 本地隧道 `127.0.0.1:17892/17893` 当前未监听
    - 不再把它们放在 `OKX` 主链路前排，避免 `connect refused` 持续污染交易链路

`mihomo` 当前职责：

- 继续作为全局 mixed-port 出口（`7890`）
- 但 `okx.com` / `okx.cab` 已在 `OKX` 专用分组中独立分流
- 当前推荐优先级：
  - `AUTO -> DIRECT`

### 0.1.1 最小巡检命令

```bash
curl -s http://127.0.0.1:9090/proxies/OKX
curl -s http://127.0.0.1:8000/api/v1/system/health
```

判读重点：

- 若 `system/health` 中出现：
  - `ClientProxyConnectionError`
  - `127.0.0.1:17892 connect error`
  - 说明配置里仍残留旧 GCP 隧道路由，应优先检查 `/etc/mihomo/config.yaml` 与 `.env`
- 若 `curl /proxies/OKX` 中 `now != AUTO`
  - 说明 `mihomo` 已把 OKX 回退到次级链路，需要继续检查当前优选节点质量
- 若 `app.log` 中没有：
  - `OKX使用环境代理: http://127.0.0.1:7890`
  - 说明交易进程未吃到当前独立 OKX 代理变量，优先检查 `.env` 与重启是否完成

---

## 1. 裸机部署

### 1.1 首次与更新

```bash
cp .env.example .env   # 编辑密钥与 MODE / TRADING_MODE；REDIS_HOST 指向本机或实际 Redis 主机
# 主调参仅使用仓库内 config/config.yaml
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
bash scripts/start-openclaw-trading.sh
# 前台调试可用：python -m src.main
# 历史入口：./start_production.sh live_trading
```

代理与 Clash：**HTTP(S)** 建议写 `http://127.0.0.1:${CLASH_MIXED_PORT:-7890}`；不稳定时不要设 `ALL_PROXY` / `OPENCLAW_ALL_PROXY`。详见 `.env.example` 与 **`deploy/HOST_CLASH_EGRESS.md`**。

全栈网络与健康链（**需 API 已在 8000 监听**）：仓库根执行 `bash scripts/verify_full_stack_network.sh`，以终端输出 **`VERIFY_FULL_STACK=PASS`** 为准。应用侧快照：`GET http://localhost:8000/api/v1/system/acceptance`；轮询脚本：`python3 scripts/startup_acceptance.py`（基址优先 **`OPENCLAW_API_BASE`**，其次 `ACCEPTANCE_BASE` / `BASE_URL`）。

### 1.2 重载配置 / 代码

修改 `config/config.yaml` 或 `src/` 后：**重启交易进程**（systemd `restart`、或 `bash scripts/stop-openclaw-trading.sh && bash scripts/start-openclaw-trading.sh`）。

### 1.3 推荐 systemd 托管

建议主服务与 health suite 一起安装：

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

核对：

```bash
systemctl status openclaw-trading.service --no-pager
systemctl list-timers --all 'openclaw-*' --no-pager
```

### 1.4 服务与端口

- **API**：默认 `0.0.0.0:8000`（本机常用 `http://127.0.0.1:8000`）  
- **Redis**：由 `.env` 的 `REDIS_HOST` / `REDIS_PORT` 指定（本机常见 `127.0.0.1:6379`）  
- **健康检查**：`curl -s http://127.0.0.1:8000/api/v1/system/health`

---

## 2. 启动到运行态检查清单

1. 进程存活：`pgrep -af "src.main|uvicorn"` 或 `systemctl status`（若已托管）  
2. `curl -s http://localhost:8000/api/v1/system/health`  
3. `curl -s http://localhost:8000/api/v1/exchanges` — OKX `is_connected`  
4. `curl -s "http://localhost:8000/api/v1/modules/commander/audit?enrich=true"` — 司令部与第三方诊断  
5. 日志: `tail -n 80 logs/app.log` — 无持续 Traceback  

> 日常托管建议直接按 `docs/DAILY_HOSTING_ACCEPTANCE.md` 执行“3~5 步”快验收。

补充（账户与持仓一致性）：

```bash
curl -s 'http://localhost:8000/api/v1/modules/commander/snapshot?symbol=BTC/USDT'
curl -s 'http://localhost:8000/api/v1/modules/commander/account-diagnostics'
```

- 若 `snapshot.data.account.positions` 为空，应检查 `snapshot.data.alerts` 是否含回退提示。
- 若 `account-diagnostics` 返回 `degraded=true` 且 `hint=account_diagnostics_timeout`，属于超时降级，不等价于“交易所断连”。

---

## 2.5 交易所实时同步与真值回填（自动，2026-05 新增）

### 2.5.1 分账原则（强制建议）

为避免排障时混淆“系统行为”和“资金事实”，请分开看两类数据源：

- **行为日志**：`logs/app.log`（决策、门控、执行、异常）
- **交易所事实账本**：`logs/exchange_sync/exchange_truth.jsonl`（pnl/fee/均价回填、fills 数量、是否估算）

### 2.5.2 自动同步线程（无需人工触发）

系统启动后会自动运行“交易所同步线程”，周期执行：

- 同步余额/持仓（用于接管与风控）
- 回填近期平仓订单的交易所真值（用于收益统计与复盘口径）

配置入口（主配置文件 `config/config.yaml`）：

- `exchange_auto_sync.enabled`（默认 true）
- `exchange_auto_sync.interval_sec`（默认 20）
- `exchange_auto_sync.truth_backfill_every_n_cycles`（默认 3）
- `exchange_auto_sync.truth_backfill_lookback_minutes`（默认 180）
- `exchange_auto_sync.truth_backfill_max_rows`（默认 80）

### 2.5.3 对账报告（值守快检）

当你怀疑“系统记录与交易所不一致”时，优先跑一键报告：

- `GET /api/v1/trades/reconcile/report?days=7&top_n=20`

超时与降级（2026-05-07 更新）：

- 若交易所不可达（常见于 TLS 校验失败、代理 MITM 根证书缺失、网络不通），对账接口可能耗时较长。
- 建议值守脚本显式设置 `timeout_sec`，避免接口卡死：
  - `GET /api/v1/trades/reconcile/report?days=7&top_n=20&timeout_sec=6`
- 超时会返回 `message=trade_reconcile_report_timeout`（结构化错误），可作为告警/降级展示依据。
- 若交易所不可达，会优先返回 `message=exchange_unreachable`（包含探针 details），避免长时间等待。

判读优先级：

1. `missing_on_exchange` 高：可能是 order_id 不完整、fills 拉取失败、或记录口径混入非实盘来源
2. `match_method=time_window` 多：说明历史链路缺少 order_id，建议优先补齐入账字段/持久化链路
3. `abs(pnl_delta)` 最大的几笔：逐笔核对交易所成交明细与系统入账

### 2.1 实时通知链路巡检（升级后必做）

> 目标：确认“行情判断、开平仓、止盈止损、告警”可同步到司令部、前端与 API 对接端。

```bash
# 1) 控制面能力与渠道契约
curl -s http://localhost:8000/api/v1/modules/commander/capabilities
curl -s http://localhost:8000/api/v1/modules/surface/channels
curl -s http://localhost:8000/api/v1/modules/surface/registry
curl -s http://localhost:8000/api/v1/auth/write-policy

# 2) A 接口（司令部统一入口）触发交易动作
TOKEN="<admin_jwt>"
curl -s -X POST http://localhost:8000/api/v1/modules/commander/dispatch \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"message":"强制开仓 BTC/USDT 0.001","source":"api_chat","timeout_sec":8}'

# 2.1) 若返回 status=timeout，改用异步模式并轮询
curl -s -X POST http://localhost:8000/api/v1/modules/commander/dispatch \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"message":"强制开仓 BTC/USDT 0.001","source":"api_chat","async_mode":true}'
curl -s 'http://localhost:8000/api/v1/modules/commander/dispatch/jobs/<job_id>'

# 3) 事件流验证（前端/API 实时消费基线）
curl -s 'http://localhost:8000/api/v1/trade/events?limit=20'

# 4) 执行审计与 SLTP 状态
curl -s http://localhost:8000/api/v1/modules/execution/production-audit
curl -s http://localhost:8000/api/v1/modules/stop-loss/stats
```

验收关键字段（至少满足）：

- `trade/events` 中出现 `trade.fill`（成交）与 `trade.position`（`sltp.create` / `sltp_stop_loss_triggered` 等）。
- `production-audit.execution_spine.last_order_*` 与最近动作一致（source/op/symbol/size/success）。
- `stop-loss/stats` 在触发后计数递增，`active_orders` 与持仓状态一致。
- `surface/channels` 与 `surface/registry` 返回成功，用于前端与第三方 API 对接配置；其中 **`registry.read_pipeline`** 为推荐只读链顺序，**`registry.api_base_env`** 标明脚本应使用的环境变量优先级。

### 2.1.1 超时治理与降级观测（2026-04-20 新增）

```bash
# 1) AI 对话链路分段耗时（trace）
curl -s -X POST http://localhost:8000/api/v1/ai/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"请简要返回当前系统状态","timeout_sec":15}'

# 2) 行情聚合快返回与降级语义
curl -s 'http://localhost:8000/api/v1/market/state?timeout_sec=3.2'

# 3) 学习反馈可观测指标
curl -s 'http://localhost:8000/api/v1/modules/ai/learning-feedback'
```

判读建议：

- `ai/chat` 关注 `data.trace.path` 与 `data.trace.*_ms`，用于确认卡点在核心路由、执行器还是直连 LLM。
- `market/state` 关注 `degraded`、`latency_ms` 与 `message`；出现 `snapshot_skipped_fast_mode` 代表主动快路径限时策略，不等价于断连。
- `learning-feedback.summary` 关注 `penalized_ratio`、`total_stop_loss_hits`、`penalty_rule.*`，判断“学习反馈”是否真实参与开仓阈值治理。

### 2.2 API / 推送 / 告警 / 记忆 二次验收（2026-04-13）

> 目标：在实盘运行底座（官方模拟下单通道）下，确认 API 连通、事件推送、告警链路、记忆读写与持久化正常。

```bash
# 0) 基础健康
curl -s http://localhost:8000/api/v1/system/health
curl -s http://localhost:8000/api/v1/s1/verify
curl -s http://localhost:8000/api/v1/modules/system/health

# 1) 推送/事件流（补偿通道）
curl -s 'http://localhost:8000/api/v1/trade/events?limit=15'

# 2) 报警链路
curl -s http://localhost:8000/api/v1/monitoring/alerts

# 3) 司令部链路与记忆系统
curl -s 'http://localhost:8000/api/v1/modules/commander/audit?enrich=true'
curl -s http://localhost:8000/api/v1/modules/commander/memory/status
curl -s 'http://localhost:8000/api/v1/modules/commander/memory/workspace?filename=COMMANDER_PROFILE.md'
curl -s http://localhost:8000/api/v1/auth/status

# 4) 记忆读写探针（写入后立即召回）
curl -s -X POST http://localhost:8000/api/v1/ai/memory/store \
  -H 'Content-Type: application/json' \
  -d '{"content":"api_acceptance_memory_probe_2026_04_13","category":"conversation","layer":"working"}'

curl -s -X POST http://localhost:8000/api/v1/ai/memory/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"api_acceptance_memory_probe_2026_04_13","limit":3}'
```

验收判定（通过标准）：

- `health` 为 `healthy`，`s1/verify` 为 `all_passed=true`。
- `trade/events` 可持续返回 `market.update`/`trade.position`/`trade.fill` 等事件。
- `monitoring/alerts` 接口可用（空列表等于“当前无活跃告警”；列表项含 `source`=`trading_monitor` 或 `enhanced_monitoring`，与 Telegram 规则告警一致）。
- `monitoring/summary` 中 `sources` 与 `enhanced_monitoring` 块可确认两路监控均已注册。
- `GET /api/v1/debug/exchange-binding` 返回当前进程内 MainController 与 DataSourceHub 绑定一致性与 ticker 探针（用于排除独立脚本与 API 进程状态不一致）。
- 记忆写入返回 `memory_id`，召回结果包含刚写入探针内容。
- `commander/memory/status` 显示分层统计与质量指标，`workspace` 读取成功。

### 2.3 监控与报警巡检

| 目标 | 命令或路径 |
|------|------------|
| 合并后的活跃告警 | `curl -s http://localhost:8000/api/v1/monitoring/alerts` |
| 摘要（含增强监控状态） | `curl -s http://localhost:8000/api/v1/monitoring/summary` |
| 告警历史 | `curl -s 'http://localhost:8000/api/v1/monitoring/alerts/history?limit=30'` |
| 进程内绑定探针 | `curl -s http://localhost:8000/api/v1/debug/exchange-binding` |

说明：**增强监控**（回撤、仓位、API 错误率等）在规则触发时会走 Telegram（若已配置）；**交易监控**侧重订单与市场数据时效。两者在 `monitoring/alerts` 中合并列出，按 `source` 区分。若 `summary.sources.enhanced_monitoring` 为 `false` 且初始化日志中有增强监控失败，应先修配置再验告警链路。

### 2.4 OpenClaw 对接上线核对（新增）

上线前建议执行：

```bash
curl -s http://localhost:8000/api/v1/modules/commander/capabilities
curl -s http://localhost:8000/api/v1/modules/commander/tool-contract
curl -s http://localhost:8000/api/v1/modules/surface/channels
curl -s http://localhost:8000/api/v1/modules/surface/registry
curl -s 'http://localhost:8000/api/v1/modules/commander/snapshot?symbol=BTC/USDT'
curl -s 'http://localhost:8000/api/v1/modules/commander/closed-loop-summary?trace_limit=120'
curl -s -X POST http://localhost:8000/api/v1/modules/commander/dispatch \
  -H 'Content-Type: application/json' \
  -d '{"message":"系统巡检","source":"openclaw","timeout_sec":8}'
```

上表 bash 已含 **交易闭环一页式摘要**（`closed-loop-summary`，只读，可选 `trace_limit`）。响应字段释义与完整对接清单见 **[OPENCLAW_INTEGRATION_GUIDE.md](./OPENCLAW_INTEGRATION_GUIDE.md)**（建议优先阅读 §2）。

补充：若 `dispatch` 在高峰期超时，建议直接使用脚本：

```bash
python3 scripts/commander_dispatch_client.py "系统巡检" --source openclaw
```

---

## 3. 网络与代理基线（Clash / 生产）

### 3.1 目标

- 本机进程经 **宿主机 Clash**：常见 `http://127.0.0.1:7890`（详细步骤与排障见 **`deploy/HOST_CLASH_EGRESS.md`**）  
- **OKX** 使用 `https://www.okx.com`，TLS 校验开启  
- DNS：避免将 OKX 解析到异常池；Clash 建议 **Rule** 模式、`fake-ip-filter` 含 `+.okx.com`

### 3.2 脚本

```bash
python3 scripts/network_connectivity_smoke.py
python3 scripts/network_connectivity_smoke.py --redis   # 需能访问 REDIS_HOST（见 .env）
python3 scripts/production_network_baseline.py --check-only
python3 scripts/production_network_baseline.py --apply   # 按脚本设计写回配置时
python3 scripts/proxy_mode_network_benchmark.py --label my_run --runs 7 --out /tmp/net.json  # TUN/代理拓扑对比
```

**裸金属生产（默认）**：`production_network_baseline.py` 的公网探针在**本机 Python** 执行，与交易进程同出口。

期望检查输出含 **`BASELINE_CHECK=PASS`**（以脚本实际提示为准）。

### 3.3 进程内代理环境

建议在 shell、systemd 或 `.env` 中导出 `HTTP(S)_PROXY` / `OPENCLAW_*_PROXY`，并保持 **`NO_PROXY=localhost,127.0.0.1,redis`**，避免 Redis 与本地健康检查走代理失败。不要将本机 API 配成 `host.docker.internal`（该名仅历史上用于容器访问宿主机）。

### 3.4 OKX 余额/持仓与进程内同步

- **密钥形态:** `config/config.yaml` 里 `exchanges.okx` 通常写 `api_key_env: OKX_API_KEY` 等指针，**真实密钥在 `.env`（或同名环境变量）**。引擎启动时会解析指针并连接 OKX；若仅写指针未导出环境变量，会报配置不完整。
- **诊断（推荐）:** `GET /api/v1/modules/commander/account-diagnostics` — 拉取前会刷新 OKX 账户缓存，便于对照交易所 App。
- **强制同步:** `POST /api/v1/modules/commander/account-sync/run`（body 可带 `reason`），会拉余额与持仓并尝试 SLTP 接管。
- **缓存:** OKX REST 对余额/持仓有短 TTL（可用 `OPENCLAW_OKX_BALANCE_CACHE_TTL` / `OPENCLAW_OKX_POSITIONS_CACHE_TTL` 调整）。下单、撤单与上述同步入口会主动失效缓存。
- **实时持仓推送（可选）:** 设置 `OPENCLAW_OKX_WS_ENABLED=1` 且 API 密钥有效时，私有频道 `positions` 推送会合并进进程内持仓视图，并触发余额缓存失效（钱包权益与仓位联动）。公共 tickers 仍用于行情快路径。

### 3.5 OKX REST 超时 / `Server disconnected` / 余额始终 0

1. **主配置必须存在**：仓库内须有 **`config/config.yaml`**。若该文件缺失，`ConfigManager` 无法合并业务段，控制面可能显示「配置为空」，OKX 密钥环境变量也可能未与 `exchanges.okx` 对齐。从 Git 恢复：`git checkout HEAD -- config/config.yaml`。本机覆盖用 **`config/local.yaml`**（勿提交）。
2. **密钥**：`.env` 中 `OKX_API_KEY`、`OKX_SECRET`、`OKX_PASSPHRASE` 须与 `config.yaml` 里 `exchanges.okx.*_env` 一致；缺密钥时 REST 会失败或返回空数据，界面表现为余额 0、无持仓。
3. **代理**：经宿主机 Clash **HTTP** 端口做 `CONNECT` 时，偶发连接被掐断。可二选一：  
   - 在 **`config/config.yaml`** 的 `proxy.okx` 下设 **`ignore_env_proxy: true`**（或环境变量 **`OPENCLAW_OKX_IGNORE_ENV_PROXY=1`**），让 OKX **仅 REST 直连**（要求本机出口可达 `www.okx.com`）；或  
   - 在 Clash 侧为 `+.okx.com` 使用稳定线路，并确认 **`fake-ip-filter`** 包含 OKX 域名（见 3.1）。  
4. **调参**：可通过 **`OPENCLAW_OKX_TIMEOUT_*`**、**`OPENCLAW_OKX_MAX_RETRIES`** 放宽超时与重试（见根目录 `.env.example`）。

### 3.6 新代理 + TUN：怎么测「哪种最好」、和旧配置差多少

**旧配置（常见痛点）**：经 **HTTP CONNECT** 的全局代理访问 OKX，易被掐、延迟高，应用里会出现 **`ticker`=`fallback`**、`unified-snapshot` 里 **`exch.*:timeout`**。

**新代理推荐拓扑**（与 `deploy/HOST_CLASH_EGRESS.md` 一致）：

1. **宿主机** Clash/mihomo 开 **TUN**（`auto-route`、Rule 分流、`fake-ip-filter` 含 `+.okx.com`）。  
2. **按基准脚本结果选优**：  
   - **A**：进程内显式 `HTTP_PROXY=http://127.0.0.1:7890`（mixed-port 建议监听 `0.0.0.0`）。  
   - **B**：TUN 已接管宿主机路由时，对 **OKX REST** 试 **`OPENCLAW_OKX_IGNORE_ENV_PROXY=1`**（或 `proxy.okx.ignore_env_proxy: true`），让 HTTPS **不经 HTTP 代理**，由 TUN/直连出口访问 `www.okx.com`（需规则允许）。

**可重复对比（改善多少用数字说话）**：

```bash
# 每种拓扑各跑一次，换 --label，得到 JSON
python3 scripts/proxy_mode_network_benchmark.py --label before_old_proxy --runs 7 --out /tmp/net_before.json
python3 scripts/proxy_mode_network_benchmark.py --label after_tun_host --runs 7 --out /tmp/net_after.json --api-base http://127.0.0.1:8000

python3 scripts/proxy_mode_network_benchmark.py --compare /tmp/net_before.json /tmp/net_after.json
```

脚本会对比 **DNS/TCP/HTTPS（尊重代理 vs 强制不走 HTTP 代理）** 的中位数延迟；若 **`no_http_proxy` 明显快于 `respect_env_proxy`**，优先采用 **TUN + 减少进程内 HTTP 代理依赖**（上文的 B）。全链路再跑：

```bash
python3 scripts/verify.py trading --base-url http://127.0.0.1:8000
```

**最优选择（当前仓库实践结论）**：**宿主机 TUN + 规则正确** 为基座；若仍大量 **CONNECT 超时**，则 **收紧 HTTP 代理依赖或 OKX 忽略环境代理**，直到 **`/api/v1/market/ticker` 的 `source` 为 `exchange` 且有价格**。

### 3.7 OKX 代理守护（可选）

仓库新增 `scripts/okx_proxy_guard.py`，用于巡检并在异常时触发 mihomo 修复动作：

```bash
python3 scripts/okx_proxy_guard.py --runs 3 --max-latency-ms 1200 --repair
```

如需常驻定时执行，可使用模板：

```bash
sudo cp deploy/systemd/okx-proxy-guard.service /etc/systemd/system/
sudo cp deploy/systemd/okx-proxy-guard.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now okx-proxy-guard.timer
```

### 3.8 系统健康审计 + 稳定性观测（推荐）

仓库新增两层只读巡检：

- `scripts/full_system_audit.py`
  - 一次性全量体检：健康接口、交易诊断、风险、账户、数据中心、日志扫描、focused pytest
- `scripts/live_stability_monitor.py`
  - 持续观测：health 漂移、OKX 可达性、LLM 熔断/回退、断连、门控拒单增长

手动执行：

```bash
.venv/bin/python scripts/full_system_audit.py
.venv/bin/python scripts/live_stability_monitor.py --interval-sec 30 --duration-min 60
```

定时执行包装脚本：

```bash
./scripts/run_scheduled_health_suite.sh audit
./scripts/run_scheduled_health_suite.sh monitor
```

输出位置：

- 审计日志：`logs/health/full_system_audit_*.log`
- 稳定性观测日志：`logs/health/live_stability_monitor_*.log`
- 观测明细：`runtime/live_stability_monitor.*.jsonl`
- 观测汇总：`runtime/live_stability_monitor.*.summary.json`
- 人类可读摘要：`logs/health/health_suite_summary.md`
- 短状态摘要：`logs/health/health_suite_status.json`

快速查看当前状态：

```bash
.venv/bin/python scripts/health_suite_status.py
cat logs/health/health_suite_status.json
```

状态约定：

- `GREEN`：审计通过，观测窗口无新增漂移
- `YELLOW`：当前窗口存在仍在增长的告警、失败审计项或 monitor warning
- `RED`：观测报错、健康状态漂移、可达性切换，或缺少关键产物

如需 systemd 定时执行，可使用模板：

```bash
sudo cp deploy/systemd/openclaw-health-audit.service /etc/systemd/system/
sudo cp deploy/systemd/openclaw-health-audit.timer /etc/systemd/system/
sudo cp deploy/systemd/openclaw-live-stability-monitor.service /etc/systemd/system/
sudo cp deploy/systemd/openclaw-live-stability-monitor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-health-audit.timer
sudo systemctl enable --now openclaw-live-stability-monitor.timer
```

说明：

- `openclaw-health-audit.timer` 默认每 `15` 分钟跑一次
- `openclaw-live-stability-monitor.timer` 默认每 `2` 小时跑一次，每次连续观测 `60` 分钟
- `full_system_audit.py` 对 `recent_disconnects` / `recent_circuit_breaks` 采用“日志累计计数 + monitor growth”联合判定
- 若日志累计高，但 `disconnect_growth=0` / `circuit_break_growth=0`，audit 会标记为 `stabilized`，不单独拖黄
- `last_order_success` 优先按 `execution_gateway.recent_events` 的最新订单事件推导；尚无订单事件时记为 `unobserved`
- 可通过环境变量调整观测窗口：

```bash
export OPENCLAW_STABILITY_MONITOR_DURATION_MIN=30
export OPENCLAW_STABILITY_MONITOR_INTERVAL_SEC=20
```

---

## 4. 日常维护

### 4.1 命令速查

```bash
curl -s http://localhost:8000/api/v1/system/health
tail -n 200 logs/app.log
./scripts/check_trading_host_health.sh
./scripts/cleanup_trading_workspace.sh   # 按需；见脚本内环境变量
```

### 4.1.1 持续巡检 + 日报（含盈利归因）

```bash
# 1) 连续巡检（建议 10~30 分钟）
python3 scripts/continuous_chain_probe.py --base-url http://127.0.0.1:8000 --duration-sec 1200 --interval-sec 20

# 2) 系统巡检日报（告警峰值 + 高频时段）
python3 scripts/system_probe_daily_summary.py \
  --input logs/system_probe_report.jsonl \
  --output logs/system_probe_daily_summary.md

# 3) 日报附加真实PnL归因（按策略/按regime + recommendations）
python3 scripts/system_probe_daily_summary.py \
  --base-url http://127.0.0.1:8000 \
  --analytics-days 30 \
  --analytics-timeout-sec 8
```

说明：

- 若交易所/API 暂时不可达，日报仍会生成，并在“盈利归因摘要”标注抓取失败原因。
- 生产建议保持 `accurate_only=true`（真实PnL优先，过滤估算样本）作为默认口径。

### 4.2 宿主机内核（可选）

降低 swap 抖动可参考仓库 `config/trading-host-sysctl.conf`（需 root 写入 `/etc/sysctl.d/` 后 `sysctl --system`）。

### 4.3 磁盘与日志

- 工作目录：`./logs`、`./data`、`./workspace`（由应用与 `logging` 配置滚动；可用 `cleanup_trading_workspace.sh` 控日志体积）

---

## 5. 排障

| 现象 | 方向 |
|------|------|
| OKX 连接失败 / SSL | 代理、DNS、Clash 规则；`production_network_baseline.py` |
| 本机无外网 / DNS 全挂 | 查 iptables、Clash **mixed-port 是否监听 `0.0.0.0`**、TUN 与路由；见 `deploy/HOST_CLASH_EGRESS.md` |
| 网络快检 | `python3 scripts/network_connectivity_smoke.py`；深度基线 `python3 scripts/production_network_baseline.py` |
| 429 过多（Reddit 等） | `OPENCLAW_THIRD_PARTY_*` 与 `OPENCLAW_REDDIT_SUBREDDIT_PAUSE_SEC` |
| Redis 错误 | 核对 `.env` 中 `REDIS_HOST`/`REDIS_PORT` 与本机 `redis-server` 或远端实例 |
| API 404（司令部 surface） | 路径须为 `/api/v1/modules/surface/...` |
| 进程锁 | 单实例运行；异常退出可检查 `/tmp/openclaw-trading.lock` |

---

## 6. 模式与安全

- **实盘** `MODE=live_trading` 前确认 API 密钥、风控与 `OKX_TESTNET`  
- 勿将 `.env` 提交仓库（已在 `.gitignore`）  
- `POST/PUT/PATCH/DELETE` 命中 `modules/monitoring/commander/trade` 前缀时默认要求 Bearer token 且角色满足写策略（默认 admin）。
- WebSocket `/ws` 默认要求 token（query/header），建议通过 `GET /api/v1/auth/write-policy` 与 `GET /api/v1/auth/status` 做上线前核对。

---

*原分散文档（Clash 基线、维护指南、生产网络说明）已合并为本页要点；细节以脚本与仓库根配置为准。*
