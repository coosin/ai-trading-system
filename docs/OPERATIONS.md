# OpenClaw Trading — 运维手册

与 [ENGINEERING.md](./ENGINEERING.md) 配合使用：本节聚焦**部署、网络、巡检与排障**。

---

## 1. Docker 部署

### 1.1 首次与更新

```bash
cp .env.example .env   # 编辑密钥与 MODE / TRADING_MODE
# 主调参仅使用仓库内 config/config.yaml；compose 已挂载 ./config:/app/config
docker compose build trading-system
docker compose up -d
```

若 **bridge 容器 DNS/出网全挂**（与宿主机 Clash 不一致），用宿主机网络跑交易服务（Redis 仍桥接并映射 `6379` 到宿主机）：

```bash
docker compose -f docker-compose.yml -f docker-compose.hostnet.yml up -d --force-recreate trading-system
# 或：./scripts/recover_trading_hostnet.sh
# 或：HOSTNET=1 ./scripts/deploy_production_stack.sh
```

`docker-compose.hostnet.yml` 处理 **网络栈 + Redis**，并注入 `OPENCLAW_DOCKER_NETWORK_HOST=1`（不把 `127.0.0.1` 误改成 `host.docker.internal`）。**默认**将 `HTTP_PROXY`/`HTTPS_PROXY`/`OPENCLAW_HTTP(S)_PROXY` 设为 `http://127.0.0.1:${CLASH_MIXED_PORT:-7890}`，并**清空** `ALL_PROXY` / `OPENCLAW_ALL_PROXY`（避免 SOCKS5 全失败拖慢请求）。覆盖：`.env` 中 `OPENCLAW_HOST_HTTP_PROXY` 或 `CLASH_MIXED_PORT`。

一键（含健康等待与 OKX 抽检）:

```bash
./scripts/deploy_production_stack.sh
```

全栈网络与健康链（Compose 已起、脚本会进容器抽检）：仓库根执行 `bash scripts/verify_full_stack_network.sh`，以终端输出 **`VERIFY_FULL_STACK=PASS`** 为准。应用侧快照：`GET http://localhost:8000/api/v1/system/acceptance`；轮询脚本：`python3 scripts/startup_acceptance.py`（可用 `ACCEPTANCE_BASE` 改基址）。宿主机 Clash/TUN 与 `host.docker.internal` 说明见 **`deploy/HOST_CLASH_EGRESS.md`**。

### 1.2 仅重载代码（卷挂载）

修改 `src/` 后：

```bash
docker compose restart trading-system
```

### 1.3 服务与端口

- **trading-system**: `8000` → API / 静态前端  
- **redis**: `6379`（内部网络 `redis:6379`）  
- **健康检查**: 容器内 `curl http://localhost:8000/health`  
- **配置卷**: `./config` → `/app/config`（修改 `config.yaml` 后 `docker compose restart trading-system` 即可，无需重建镜像）

---

## 2. 启动到运行态检查清单

1. `docker ps` — `openclaw-trading` 为 `healthy`  
2. `curl -s http://localhost:8000/health`  
3. `curl -s http://localhost:8000/api/v1/exchanges` — OKX `is_connected`  
4. `curl -s "http://localhost:8000/api/v1/modules/commander/audit?enrich=true"` — 司令部与第三方诊断  
5. 日志: `docker logs openclaw-trading --tail 80` — 无持续 Traceback  

### 2.1 实时通知链路巡检（升级后必做）

> 目标：确认“行情判断、开平仓、止盈止损、告警”可同步到司令部、前端与 API 对接端。

```bash
# 1) 控制面能力与渠道契约
curl -s http://localhost:8000/api/v1/modules/commander/capabilities
curl -s http://localhost:8000/api/v1/modules/surface/channels
curl -s http://localhost:8000/api/v1/modules/surface/registry

# 2) A 接口（司令部统一入口）触发交易动作
curl -s -X POST http://localhost:8000/api/v1/modules/commander/dispatch \
  -H 'Content-Type: application/json' \
  -d '{"message":"强制开仓 BTC/USDT 0.001","source":"api_chat"}'

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
- `surface/channels` 与 `surface/registry` 返回成功，用于前端与第三方 API 对接配置。

### 2.2 API / 推送 / 告警 / 记忆 二次验收（2026-04-13）

> 目标：在实盘运行底座（官方模拟下单通道）下，确认 API 连通、事件推送、告警链路、记忆读写与持久化正常。

```bash
# 0) 基础健康
curl -s http://localhost:8000/health
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
- `monitoring/alerts` 接口可用（空列表等于“当前无活跃告警”）。
- 记忆写入返回 `memory_id`，召回结果包含刚写入探针内容。
- `commander/memory/status` 显示分层统计与质量指标，`workspace` 读取成功。

---

## 3. 网络与代理基线（Clash / 生产）

### 3.1 目标

- 容器访问外网经 **宿主机 Clash**：`host.docker.internal:7890`（见 `docker-compose.yml` `extra_hosts`；详细步骤与排障见 **`deploy/HOST_CLASH_EGRESS.md`**）  
- **OKX** 使用 `https://www.okx.com`，TLS 校验开启  
- DNS：避免将 OKX 解析到异常池；Clash 建议 **Rule** 模式、`fake-ip-filter` 含 `+.okx.com`

### 3.2 脚本

```bash
python3 scripts/network_connectivity_smoke.py
python3 scripts/network_connectivity_smoke.py --redis   # 需能访问 REDIS_HOST（如 compose 内 redis）
python3 scripts/production_network_baseline.py --check-only
python3 scripts/production_network_baseline.py --apply   # 按脚本设计写回配置时
python3 scripts/proxy_mode_network_benchmark.py --label my_run --runs 7 --out /tmp/net.json  # TUN/代理拓扑对比
```

期望检查输出含 **`BASELINE_CHECK=PASS`**（以脚本实际提示为准）。

### 3.3 容器内代理环境

Compose 已注入 `HTTP(S)_PROXY` / `OPENCLAW_*_PROXY` 与 `NO_PROXY=localhost,127.0.0.1,redis`。若自定义，请保持 **Redis 与 localhost 不走代理**，否则健康检查与内网会失败。

### 3.4 OKX REST 超时 / `Server disconnected` / 余额始终 0

1. **主配置必须存在**：仓库内须有 **`config/config.yaml`**（挂载到容器 `/app/config`）。若该文件缺失，`ConfigManager` 无法合并业务段，控制面可能显示「配置为空」，OKX 密钥环境变量也可能未与 `exchanges.okx` 对齐。从 Git 恢复：`git checkout HEAD -- config/config.yaml`。本机覆盖用 **`config/local.yaml`**（勿提交）。
2. **密钥**：`.env` 中 `OKX_API_KEY`、`OKX_SECRET`、`OKX_PASSPHRASE` 须与 `config.yaml` 里 `exchanges.okx.*_env` 一致；缺密钥时 REST 会失败或返回空数据，界面表现为余额 0、无持仓。
3. **代理**：经宿主机 Clash **HTTP** 端口做 `CONNECT` 时，偶发连接被掐断。可二选一：  
   - 在 **`config/config.yaml`** 的 `proxy.okx` 下设 **`ignore_env_proxy: true`**（或环境变量 **`OPENCLAW_OKX_IGNORE_ENV_PROXY=1`**），让 OKX **仅 REST 直连**（要求容器出口可达 `www.okx.com`）；或  
   - 在 Clash 侧为 `+.okx.com` 使用稳定线路，并确认 **`fake-ip-filter`** 包含 OKX 域名（见 3.1）。  
4. **调参**：可通过 **`OPENCLAW_OKX_TIMEOUT_*`**、**`OPENCLAW_OKX_MAX_RETRIES`** 放宽超时与重试（见根目录 `.env.example`）。

### 3.5 新代理 + TUN：怎么测「哪种最好」、和旧配置差多少

**旧配置（常见痛点）**：Docker **bridge** + 仅 **`HTTP_PROXY=http://host.docker.internal:7890`**。OKX 等走 **HTTP CONNECT**，易被掐、延迟高，应用里会出现 **`ticker`=`fallback`**、`unified-snapshot` 里 **`exch.*:timeout`**。

**新代理推荐拓扑**（与 `deploy/HOST_CLASH_EGRESS.md` 一致）：

1. **宿主机** Clash/mihomo 开 **TUN**（`auto-route`、Rule 分流、`fake-ip-filter` 含 `+.okx.com`）。  
2. **二选一（按基准脚本结果选优）**：  
   - **A**：容器仍用 bridge + `HTTP_PROXY`（适合只改代理、不动 compose）。  
   - **B**：交易容器 **`network_mode: host`**（`docker-compose.hostnet.yml`），`.env` 里代理指 **`127.0.0.1:7890`**，并依赖 **`OPENCLAW_DOCKER_NETWORK_HOST=1`** 避免把环回误改写成 `host.docker.internal`。  
   - **C**：TUN 已接管宿主机路由时，对 **OKX REST** 试 **`OPENCLAW_OKX_IGNORE_ENV_PROXY=1`**（或 `proxy.okx.ignore_env_proxy: true`），让 HTTPS **不经 HTTP 代理**，由 TUN/直连出口访问 `www.okx.com`（需规则允许）。

**可重复对比（改善多少用数字说话）**：

```bash
# 每种拓扑各跑一次，换 --label，得到 JSON
python3 scripts/proxy_mode_network_benchmark.py --label before_old_proxy --runs 7 --out /tmp/net_before.json
python3 scripts/proxy_mode_network_benchmark.py --label after_tun_host --runs 7 --out /tmp/net_after.json --api-base http://127.0.0.1:8000

python3 scripts/proxy_mode_network_benchmark.py --compare /tmp/net_before.json /tmp/net_after.json
```

脚本会对比 **DNS/TCP/HTTPS（尊重代理 vs 强制不走 HTTP 代理）** 的中位数延迟；若 **`no_http_proxy` 明显快于 `respect_env_proxy`**，优先采用 **TUN + 减少容器内 HTTP 代理依赖**（上文的 B 或 C）。全链路再跑：

```bash
python3 scripts/full_system_integration_check.py
```

**最优选择（当前仓库实践结论）**：**宿主机 TUN + 规则正确** 为基座；容器侧若仍大量 **CONNECT 超时**，则 **host 网络或 OKX 忽略环境代理** 二选一或组合，直到 **`/api/v1/market/ticker` 的 `source` 为 `exchange` 且有价格**。

---

## 4. 日常维护

### 4.1 命令速查

```bash
curl -s http://localhost:8000/health
docker logs openclaw-trading --tail 200
./scripts/check_trading_host_health.sh
./scripts/cleanup_trading_workspace.sh   # 按需；见脚本内环境变量
```

### 4.2 宿主机内核（可选）

降低 swap 抖动可参考仓库 `config/trading-host-sysctl.conf`（需 root 写入 `/etc/sysctl.d/` 后 `sysctl --system`）。

### 4.3 磁盘与日志

- 挂载目录：`./logs`、`./data`、`./workspace`  
- Compose 日志驱动 `json-file`，`max-size` / `max-file` 已限制滚动  

---

## 5. 排障

| 现象 | 方向 |
|------|------|
| OKX 连接失败 / SSL | 代理、DNS、Clash 规则；`production_network_baseline.py` |
| 容器完全无外网 / DNS 全挂 | 先试 `docker-compose.hostnet.yml`（上 1.1）；再查 iptables、Clash **mixed-port 是否监听 `0.0.0.0`**（仅 `127.0.0.1` 时 bridge 常连不上代理，见 `deploy/HOST_CLASH_EGRESS.md` §4） |
| 容器内快速自检 | `docker exec openclaw-trading sh /app/scripts/diagnose_container_net.sh`（含 `ping`/`ip`；改 Dockerfile 后需 **`docker compose build trading-system`**） |
| 429 过多（Reddit 等） | `OPENCLAW_THIRD_PARTY_*` 与 `OPENCLAW_REDDIT_SUBREDDIT_PAUSE_SEC` |
| Redis 错误 | `REDIS_HOST=redis`、服务是否 healthy |
| API 404（司令部 surface） | 路径须为 `/api/v1/modules/surface/...` |
| 进程锁 | 容器内单实例；异常退出可检查 `/tmp/openclaw-trading.lock` |

---

## 6. 模式与安全

- **实盘** `MODE=live_trading` 前确认 API 密钥、风控与 `OKX_TESTNET`  
- 勿将 `.env` 提交仓库（已在 `.gitignore`）  

---

*原分散文档（Clash 基线、维护指南、生产网络说明）已合并为本页要点；细节以脚本与 `docker-compose.yml` 为准。*
