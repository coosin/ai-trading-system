# OpenClaw Trading — 运维手册

与 [ENGINEERING.md](./ENGINEERING.md) 配合使用：本节聚焦**部署、网络、巡检与排障**。

---

## 1. Docker 部署

### 1.1 首次与更新

```bash
cp .env.example .env   # 编辑密钥与 MODE
docker compose build trading-system
docker compose up -d
```

一键（含健康等待与 OKX 抽检）:

```bash
./scripts/deploy_production_stack.sh
```

### 1.2 仅重载代码（卷挂载）

修改 `src/` 后：

```bash
docker compose restart trading-system
```

### 1.3 服务与端口

- **trading-system**: `8000` → API / 静态前端  
- **redis**: `6379`（内部网络 `redis:6379`）  
- **健康检查**: 容器内 `curl http://localhost:8000/health`

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

- 容器访问外网经 **宿主机 Clash**：`host.docker.internal:7890`（见 `docker-compose.yml` `extra_hosts`）  
- **OKX** 使用 `https://www.okx.com`，TLS 校验开启  
- DNS：避免将 OKX 解析到异常池；Clash 建议 **Rule** 模式、`fake-ip-filter` 含 `+.okx.com`

### 3.2 脚本

```bash
python3 scripts/production_network_baseline.py --check-only
python3 scripts/production_network_baseline.py --apply   # 按脚本设计写回配置时
```

期望检查输出含 **`BASELINE_CHECK=PASS`**（以脚本实际提示为准）。

### 3.3 容器内代理环境

Compose 已注入 `HTTP(S)_PROXY` / `OPENCLAW_*_PROXY` 与 `NO_PROXY=localhost,127.0.0.1,redis`。若自定义，请保持 **Redis 与 localhost 不走代理**，否则健康检查与内网会失败。

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
