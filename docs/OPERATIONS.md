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
docker compose -f docker-compose.yml -f docker-compose.hostnet.yml up -d
# 或：HOSTNET=1 ./scripts/deploy_production_stack.sh
```

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
| 容器完全无外网 / DNS 全挂 | 先试 `docker-compose.hostnet.yml`（上 1.1）；再查 iptables、Clash 是否监听 `0.0.0.0`、`host.docker.internal`（见 `deploy/HOST_CLASH_EGRESS.md`） |
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
