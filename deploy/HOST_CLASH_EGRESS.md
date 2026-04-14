# 宿主机 Clash / mihomo：网卡流量接管与分流（推荐架构）

交易程序**不负责**劫持网卡；应在**服务器本机**运行的 Clash Verge / mihomo / sing-box 等上完成 **TUN 模式 + 系统路由**，实现：

- 全局出站经代理核心按 **规则（RULE）** 分流（国内直连、海外代理、OKX/API 等可细分）；
- 可选 **强制走代理**（仅代理、无直连）以满足合规或专线场景。

以下以 **mihomo（Clash Meta 内核）** 为例；原版 Clash Premium 思路相同，字段名可能略有差异。

---

## 1. 核心思路

| 能力 | 实现位置 |
|------|----------|
| 绑定网卡 / 接管本机 TCP 出站 | 宿主机 **TUN 虚拟网卡** + 系统路由表（`auto-route`） |
| 域名 / IP / GEOIP 分流 | 代理内核 **routing / rules** |
| Docker 内业务进程 | **方案 A**：容器仍设 `HTTP_PROXY` 指向 `host.docker.internal:端口`；**方案 B**：`network_mode: host` 让容器继承宿主机已劫持的路由（注意端口冲突与安全面） |

本仓库 `config/config.yaml` 里的 `proxy` 段 = **应用进程**对 HTTP 客户端的补充（`NO_PROXY` 合并等）；**与宿主机 TUN 互补，不替代 TUN。**

---

## 2. mihomo 最小 TUN 片段（示例，需自行合并进完整配置）

```yaml
# 全局：工作模式建议 RULE（规则分流）
mode: Rule

tun:
  enable: true
  # system：由内核接管路由，适合「整台机器出站走 Clash」
  stack: system
  auto-route: true
  auto-redirect: true
  auto-detect-interface: true
  # 严格全局时可关闭 strict-route 的例外需查阅你使用的内核版本文档
  strict-route: false
  dns-hijack:
    - "any:53"

# 入站：本机 HTTP/SOCKS 混合端口，给 Docker 里只认环境变量的程序用
mixed-port: 7890

# 下面必须有：proxy-providers / proxies、rules 等，此处省略
```

启用 TUN 后，**通常需要 root / 管理员**或赋予 mihomo **NET_ADMIN** 能力（systemd、Docker 宿主机安装方式见各发行版文档）。

---

## 3. 分流（RULE）在代理软件里写

在 **`rules:`** 里按优先级写，例如（示意，非完整）：

- `DOMAIN-SUFFIX,okx.com,DIRECT` 或走你的专线 `PROXY`；
- `GEOIP,CN,DIRECT`；
- `MATCH,PROXY` 兜底。

**「强制全部走代理」**：去掉/收紧 `DIRECT` 规则，或把 `MATCH` 指向唯一策略组。

具体语法以你使用的 **mihomo / Clash 文档** 为准。

---

## 4. 与本项目 Docker Compose 的配合

1. 宿主机 Clash 监听 **7890**（或你自定义的 mixed-port）。
2. Compose 中交易容器已通过 `extra_hosts: host.docker.internal:host-gateway`，`config/proxy.global_proxy.host` 默认 **`host.docker.internal`**，即 **容器 → 宿主机 Clash**。
3. **`network_mode: host` 与 `networks:`**：本仓库用根目录 **`docker-compose.hostnet.yml`**（`networks: !reset null` 等）与基座 **合并**，让交易服务走宿主机网络栈且 **Redis 仍为 compose 桥接**。推荐：

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.hostnet.yml up -d --force-recreate trading-system
   ```

   **勿**用裸 `docker run --network host` 替代整套 compose（易丢卷、`.env`、`depends_on`、Redis 约定）。一键：`./scripts/recover_trading_hostnet.sh`。

4. **Clash / mihomo 的 mixed-port 若只监听 `127.0.0.1`**：bridge 容器通过 `host.docker.internal`（宿主机在 docker 网上的地址）去连 **经常失败**——目标端口在回环上，对「从容器来的」连接不可达。处理：让入站监听 **`0.0.0.0:7890`**（或等价），或改用 **`docker-compose.hostnet.yml`**，在进程内直接使用 **`http://127.0.0.1:7890`**。

5. **bridge + 显式 HTTP 代理**（代理对 docker 网可达时）：与宿主机 TUN **可同时存在**——TUN 管宿主机进程，容器内 HTTP 库走 `HTTP_PROXY`，便于验收与排障。

---

## 5. 验收时怎么说明

- **「强制绑定网卡、接管分流」** → 在 **宿主机 Clash 配置（TUN + rules）** 中验收，不在 Python 代码里验收。
- 应用侧验收仍可用：`GET /api/v1/system/acceptance` 与 `scripts/startup_acceptance.py`，确认 **主配置与 Redis/模块** 就绪；网络策略以 **宿主机代理配置审计** 为准。

---

## 6. 参考（外部链接）

- mihomo TUN：<https://wiki.metacubex.one/config/tun/>
- Clash Meta 路由与规则：以你所用发行版 Wiki 为准。

若你们有**固定规则集 / 订阅命名规范**，建议单独维护一份「生产环境 Clash 配置」Git 仓库，本仓库仅引用端口与宿主机 IP 约定。

---

## 7. 与「仅 HTTP 代理」对比：可重复基准

开启 TUN 前后、或改 compose 前后，用同一脚本各跑一次并 `--compare` 两次 JSON，可看 **DNS/TCP/HTTPS 中位数延迟** 与 **是否仍依赖 HTTP 代理更快**。详见 **`docs/OPERATIONS.md`** §3.5 与仓库 **`scripts/proxy_mode_network_benchmark.py`**。
