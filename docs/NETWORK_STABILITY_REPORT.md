# 网络与代理连接稳定性分析报告

本文档汇总典型故障现象、根因假设、与仓库当前配置（`docker-compose.yml`、`config/config.yaml`、环境变量）的对应关系，并给出**可执行**的修复与架构选项。运维细节另见 [OPERATIONS.md](./OPERATIONS.md)；宿主机 Clash/TUN 见 [../deploy/HOST_CLASH_EGRESS.md](../deploy/HOST_CLASH_EGRESS.md)。

---

## 1. 测试结果汇总（示例场景）

以下表格适用于「宿主机已验证公网/代理可用，但容器内异常」的对比排查。**实际结论必须以你机器上的 `docker exec` / `curl` / 日志为准。**

### 1.1 表现正常的连接（宿主机侧）

| 服务 | 典型状态 | 说明 |
|------|----------|------|
| OKX REST | ✅ | `https://www.okx.com` 在宿主机 `curl` 正常 |
| Binance REST | ✅ | `https://api.binance.com` 宿主机可达 |
| CoinGecko REST | ✅ | `https://api.coingecko.com` 宿主机可达 |
| DNS | ✅ | 宿主机 `dig`/`nslookup` 解析预期 |
| Clash（宿主机） | ✅/⚠️ | 混合端口可访问 ≠ 容器内 `CONNECT` 一定稳定 |

### 1.2 表现异常或需区分根因的连接

| 现象 | 可能状态 | 常见原因（非唯一） |
|------|----------|-------------------|
| 容器内无外网 | ❌ | 防火墙/NAT/iptables、`userland-proxy`、企业策略、错误 `HTTP_PROXY` 指向不可达地址导致**首跳即失败** |
| 容器内 DNS 失败 | ❌ | 宿主机或 Docker `daemon.json` DNS、公司内网劫持、`dns_search` 污染 |
| `host.docker.internal:7890` 不可达 | ❌ | Linux 上需 `extra_hosts: host-gateway`（**本仓库 compose 已加**）；或宿主机 Clash 未监听 `0.0.0.0:7890` |
| HTTP 经代理 `Server disconnected` | ⚠️ | Clash HTTP CONNECT 与 aiohttp/httpx 长连接/半开连接；**不等价于**「容器完全没网」 |
| OKX/Binance **WebSocket** | ⚠️ | 多经 `wss`，需 TLS + 代理对 WebSocket 的支持；REST 正常时 WS 仍可能单独失败 |
| OpenAI / 讯飞等 LLM | ⚠️ 401 | **鉴权问题**（密钥、base_url）；与「有无外网」分开验证 |
| OpenAI `RemoteProtocolError` | ⚠️ | 代理断开、keep-alive；可用环境变量做直连回退（见第 4 节） |

---

## 2. 根因分析（分层）

### 2.1 容器「完全没网」vs「有网但代理/HTTPS 失败」

必须先区分：

1. **真·无出口**：容器内 `ping 1.1.1.1`、`curl -I https://1.1.1.1`（或 `curl https://www.okx.com`）均失败 → 查 Docker 网桥、iptables、`ufw`、云厂商安全组、VPN 分流。
2. **有出口但走代理失败**：直连公网 OK，一设 `HTTP_PROXY` 就失败 → 查 `host.docker.internal`、Clash 端口、`CONNECT`、节点。
3. **有出口、直连 OK、仅部分域名失败** → 查 DNS（fake-ip）、Clash 规则、地域限制。

### 2.2 当前 Compose 网络与 DNS（事实基线）

根目录 `docker-compose.yml` 中 `trading-system` 已配置：

- **自定义桥接网络** `trading-network`（项目名前缀后实际名类似 `openclaw-trading_trading-network`）。
- **DNS**：`1.1.1.1`、`8.8.8.8`；`dns_search: []`（减少无效 search 后缀干扰）。
- **`extra_hosts`**：`host.docker.internal:host-gateway`（Linux 上解析到宿主机网关，供访问宿主机 Clash）。

若仍出现「容器 DNS 全失败」，问题多在**宿主机 Docker 守护进程**或**上游网络策略**，而非应用代码。

### 2.3 代理与进程环境变量

- Compose 注入 `HTTP_PROXY` / `HTTPS_PROXY`（来自 `.env` 的 `OPENCLAW_HTTP_PROXY` 等）。
- `config/config.yaml` 的 `proxy` 段可通过 `apply_to_process_env` **合并/注入**进程环境（见 `network_env_from_config`）。
- **OKX 单独策略**：`proxy.okx.ignore_env_proxy: true` 会设置 `OPENCLAW_OKX_IGNORE_ENV_PROXY=1`，使 OKX REST **忽略环境 HTTP(S)_PROXY**（需容器出口本身可达 OKX）。

> **注意**：主配置里**没有**名为 `proxy.openai.ignore_env_proxy` / `proxy.binance.ignore_env_proxy` 的通用键。  
> LLM 侧应使用环境变量 **`OPENCLAW_LLM_DIRECT_FALLBACK=1`**（见 `.env.example`），在代理类错误后对该 Provider 切换**无代理 httpx**（需容器能直连模型 `base_url`）。

### 2.4 WebSocket

REST 与 WSS 路径不同：WSS 常受 **代理对 Upgrade/WebSocket 的支持**、**TLS 中间盒** 影响。防火墙封 **9443/8443** 在部分环境存在，但更多见的是 **代理/规则** 问题而非单纯「端口未开」。

---

## 3. 解决方案（按推荐顺序）

### 方案 A：在桥接网络下修复「宿主机代理可达性」（改动最小）

1. **确认 Clash 监听地址**  
   若只监听 `127.0.0.1:7890`，容器经 `host.docker.internal` 访问的是**宿主机在 bridge 上的网关 IP**，需 Clash 对**局域网/网关接口**可达（常见做法：mixed-port 监听 `0.0.0.0` 或明确允许 Docker 网段）。

2. **验证容器内三步**（在 `openclaw-trading` 内执行）  
   - `getent hosts host.docker.internal`  
   - `nc -zv host.docker.internal 7890` 或 `curl -x http://host.docker.internal:7890 -I https://www.google.com`  
   - 无代理：`curl -I https://www.okx.com`

3. **网络抖动**  
   已在本仓库加强：`data_integration`（Binance/CoinGecko）TLS 与重试、OKX REST 连接器与断开重试、LLM 可选直连回退。拉最新镜像/代码后重启容器。

### 方案 B：`network_mode: host`（Linux，效果强，需改 Redis 访问方式）

**优点**：与宿主机同一网络栈；`HTTP_PROXY=http://127.0.0.1:7890` 行为与宿主机进程一致；不依赖 `host.docker.internal`。

**必改点**：

- 当前 compose 中 `REDIS_HOST=redis` 依赖 **Docker 内置 DNS** 解析服务名；**host 网络下 `redis` 主机名通常不存在**。  
  应改为例如：  
  - `REDIS_HOST=127.0.0.1` 且 Redis 端口映射到宿主机，或  
  - Redis 同样使用 host 网络且监听 `127.0.0.1:6379`，或  
  - 使用宿主机实际 IP。  
- **端口冲突**：host 模式下容器内 `8000` 即宿主机 `8000`，需避免冲突。  
- **depends_on / healthcheck**：仅表示启动顺序，host 网络下仍须保证 Redis 已监听。

建议在单独 `docker-compose.hostnet.yml` 或 profile 中维护，避免破坏默认 bridge 部署。

### 方案 C：Docker 守护进程级 DNS（当「仅容器 DNS 坏」时）

在 `/etc/docker/daemon.json` 中配置 `dns` 后 **`systemctl restart docker`**。  
注意：这是**全局**行为，需运维评估；与 compose 内 `dns:` 可同时存在，以实际生效顺序为准。

### 方案 D：不在容器内运行（裸机 / systemd）

**可能改善**：少一层 bridge、代理用 `127.0.0.1`、与宿主机 TUN 路由完全一致。  
**不保证**：若根因是节点质量、DNS fake-ip、API 限流，裸机同样失败。  
**代价**：依赖隔离变弱，Python/系统库版本需自行约束。

---

## 4. 与本仓库相关的环境变量速查

| 变量 | 作用 |
|------|------|
| `OPENCLAW_OKX_IGNORE_ENV_PROXY=1` | OKX REST 忽略环境代理（可与 `config.proxy.okx.ignore_env_proxy: true` 同步） |
| `OPENCLAW_LLM_DIRECT_FALLBACK=1` | LLM（OpenAI 兼容路径）代理失败/超时后尝试**直连** |
| `OPENCLAW_DATASOURCE_HTTP_TIMEOUT` / `OPENCLAW_DATASOURCE_MAX_RETRIES` | Binance/CoinGecko 辅助行情超时与重试 |

详见根目录 `.env.example`。

---

## 5. 建议的监控与验证（运维）

在容器内定期或手工执行：

```bash
# DNS
getent hosts www.okx.com api.binance.com api.coingecko.com

# 无代理直连
curl -sS -o /dev/null -w "%{http_code}\n" --max-time 15 https://www.okx.com/

# 经宿主机 Clash HTTP 端口（按你实际地址改）
curl -sS -o /dev/null -w "%{http_code}\n" --max-time 20 -x http://host.docker.internal:7890 https://www.google.com/

# 仓库脚本
python3 scripts/network_connectivity_smoke.py --redis --api-url http://127.0.0.1:8000/health
```

全栈：`bash scripts/verify_full_stack_network.sh`（需 compose 与脚本在仓库内完整）。

---

## 6. 立即行动清单（优先级）

| 优先级 | 动作 |
|--------|------|
| P0 | 在容器内区分「无出口」还是「仅代理失败」（上节命令） |
| P0 | 确认 Clash 对 Docker 网段/`host.docker.internal` 可达；或改用 **host 网络 + 127.0.0.1 代理 + 修正 REDIS_HOST** |
| P1 | 对 OKX：按需开启 `proxy.okx.ignore_env_proxy`；对 LLM：按需 `OPENCLAW_LLM_DIRECT_FALLBACK=1` |
| P1 | 宿主机 Clash：**TUN + rules + fake-ip-filter 含交易所/LLM 域名**（见 HOST_CLASH_EGRESS） |
| P2 | 401 类：单独配置有效 API Key / base_url，勿与网络问题混为一谈 |

---

## 7. 总结

- **核心矛盾**往往是：**桥接网络 + 宿主机 HTTP 代理 + CONNECT 稳定性 + DNS**，而不是「Python 写错了」单点问题。  
- **容器并非必然更差**；配置正确时 bridge + `host-gateway` 足够。若环境特殊，**host 网络**或 **裸机** 可减少一层变量。  
- **REST 与 WebSocket、鉴权(401)与网络断开** 应分开结论，避免一次误判掩盖真正原因。

---

*文档版本与仓库行为对齐；若 Compose 或 `proxy` 段变更，请同步更新本节「事实基线」。*
