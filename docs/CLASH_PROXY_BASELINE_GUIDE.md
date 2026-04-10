# Clash 代理基线设置与排障指南（生产固化版）

本文档固化本项目已验证稳定的代理方案，目标是：

- 避免误操作导致生产链路抖动
- 快速恢复到可用基线
- 提供统一排障步骤（OKX / Binance / 三方数据）

---

## 1. 目标基线（必须满足）

### 1.1 Clash 主配置基线

- `mode: Rule`
- `🚀 节点选择` 当前值应为 `♻️ 自动选择`
- DNS 开启增强与稳定策略：
  - `enhanced-mode: fake-ip`
  - `listen: 0.0.0.0:1053`（避免 53 端口冲突）
  - `fake-ip-filter` 含 `+.okx.com`、`+.okex.com`
  - `nameserver-policy` 对 `+.okx.com`、`+.okex.com` 使用 **1.1.1.1**（或同等可信 DoH），**不要**用 119/223/114/8.8.8.8 单独作为 OKX 策略：在部分网络会解析到 `awscn.okpool.top` → `169.254.0.2`，导致握手异常、Cloudflare `530` / `error code: 1016`

### 1.2 容器代理环境基线（docker-compose）

`trading-system` 必须包含：

- `OPENCLAW_HTTP_PROXY=http://host.docker.internal:7890`
- `OPENCLAW_HTTPS_PROXY=http://host.docker.internal:7890`
- `OPENCLAW_ALL_PROXY=http://host.docker.internal:7890`
- `NO_PROXY=localhost,127.0.0.1,redis`

并且清空系统代理变量（防污染）：

- `HTTP_PROXY=`
- `HTTPS_PROXY=`
- `ALL_PROXY=`
- `http_proxy=`
- `https_proxy=`
- `all_proxy=`

### 1.3 应用层网络/TLS基线

- OKX 统一使用 `https://www.okx.com`
- 请求启用证书校验（禁止 `ssl=False`）
- TLS 上下文统一使用系统/`certifi` CA，最低 TLS1.2
- 连接失败具备自动自愈（重试、会话重建、必要时切换代理源）

---

## 2. 一键固化（推荐）

项目已提供基线脚本：

```bash
python3 scripts/production_network_baseline.py --apply
```

检查模式（不改配置）：

```bash
python3 scripts/production_network_baseline.py --check-only
```

通过标志：

- 输出 `BASELINE_CHECK=PASS`

失败标志：

- 输出 `BASELINE_CHECK=FAIL`（根据输出项逐条修复）

---

## 3. 生产日常操作建议

### 3.1 何时必须执行 `--apply`

- 更新 Clash 订阅后
- 修改 `/etc/clash/config.yaml` 后
- 改动 `docker-compose.yml` 网络/环境变量后
- 容器重建后发现交易所连接波动

### 3.2 日常巡检频率

- 建议至少每日执行 1 次：

```bash
python3 scripts/production_network_baseline.py --check-only
```

### 3.3 升级与变更原则

- 先 `--check-only` 记录现状
- 再做变更
- 变更后立即 `--apply` 回归
- 确认 `BASELINE_CHECK=PASS` 再继续交易

---

## 4. 标准排障流程（从快到慢）

### Step 1：看基础存活

```bash
docker compose ps
curl -m 10 http://127.0.0.1:8000/health
```

预期：

- `openclaw-trading` / `openclaw-redis` 为 `healthy`
- `/health` 返回 `{"status":"healthy", ...}`

### Step 2：看容器代理变量

```bash
docker exec -i openclaw-trading python - <<'PY'
import os
for k in ["OPENCLAW_HTTP_PROXY","OPENCLAW_HTTPS_PROXY","OPENCLAW_ALL_PROXY","NO_PROXY"]:
    print(k, "=", os.getenv(k))
PY
```

如果为空或错误，优先修复 `docker-compose.yml`。

### Step 3：看 Clash 当前选择

```bash
python3 - <<'PY'
import json, urllib.request
j=json.load(urllib.request.urlopen("http://127.0.0.1:9090/proxies"))
print("节点选择:", j["proxies"].get("🚀 节点选择",{}).get("now"))
print("自动选择:", j["proxies"].get("♻️ 自动选择",{}).get("now"))
PY
```

预期：`节点选择` 为 `♻️ 自动选择`。

### Step 4：接口连通验证（代理 + TLS）

```bash
docker exec -i openclaw-trading python - <<'PY'
import os, requests
p=os.getenv("OPENCLAW_HTTP_PROXY")
targets=[
    "https://www.okx.com/api/v5/public/time",
    "https://api.binance.com/api/v3/time",
    "https://api.coingecko.com/api/v3/ping",
    "https://api.coinbase.com/v2/time",
    "https://api.kraken.com/0/public/Time",
]
for u in targets:
    try:
        r=requests.get(u, proxies={"http":p,"https":p}, timeout=10, verify=True)
        print(u, r.status_code)
    except Exception as e:
        print(u, "ERR", repr(e))
PY
```

### Step 5：回到基线（最稳）

```bash
python3 scripts/production_network_baseline.py --apply
```

---

## 5. 常见问题与结论

### Q1：为什么 `api.okx.com` 失败，而 `www.okx.com` 正常？

在当前线路下，`api.okx.com` 可能受 CDN/策略影响（如 530、SSL EOF）。  
生产上以 `www.okx.com` 为准。

### Q2：为什么容器直连经常 `Network is unreachable`？

这是环境网络路径特征。生产应使用已固化代理链路，不依赖直连。

### Q3：Binance 偶发失败 1 次是否正常？

节点短时抖动可出现偶发失败；若连续失败升高，执行 `--apply` 并观察探针结果。

### Q4：NewsAPI 返回 401 是代理问题吗？

不是。通常是 `NEWS_API_KEY` 缺失或无效。

---

## 6. 变更审计建议

建议记录以下内容到运维日志：

- 执行人、时间
- 是否执行 `--apply` 或 `--check-only`
- `BASELINE_CHECK` 结果
- 关键探针成功率（ok/fail）

---

## 7. 快速命令清单

```bash
# 一键固化
python3 scripts/production_network_baseline.py --apply

# 只检查
python3 scripts/production_network_baseline.py --check-only

# 服务状态
docker compose ps

# 应用健康
curl -m 10 http://127.0.0.1:8000/health
```

