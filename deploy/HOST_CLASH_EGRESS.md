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
| 本机业务进程（Python 交易 API） | **环境变量**：`HTTP_PROXY`/`HTTPS_PROXY` 指向 **`http://127.0.0.1:端口`**（与 mihomo **mixed-port** 一致）；保持 **`NO_PROXY=localhost,127.0.0.1,redis`**；**`host.docker.internal` 仅历史上用于旧容器场景，裸机勿用** |

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

# 入站：本机 HTTP/SOCKS 混合端口，给只认环境变量的程序用
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

## 4. 与本项目裸机进程的配合

1. 宿主机 Clash 监听 **7890**（或你自定义的 mixed-port）；建议 mixed-port 监听 **`0.0.0.0`**，避免仅 `127.0.0.1` 时与其它组件的入站策略冲突。  
2. 交易进程在 **本机 Python** 中运行：在 `.env` 或 systemd 中设置 **`OPENCLAW_HTTP_PROXY`/`OPENCLAW_HTTPS_PROXY`** 或标准 **`HTTP_PROXY`/`HTTPS_PROXY`** 为 **`http://127.0.0.1:7890`**（端口与 Clash 一致）。  
3. **`REDIS_HOST`**：本机 Redis 填 **`127.0.0.1`**；远端填实际主机名。  
4. **TUN 与显式 HTTP 代理可同时存在**：TUN 管系统路由，Python HTTP 客户端仍可按环境变量走 mixed-port，便于验收与排障。

### 4.1 OKX DNS 异常（169.254.x.x / 198.18.x.x）

- **`www.okx.com` → `169.254.0.2` 等链路本地地址**：多为 **DNS 污染/劫持**（部分运营商递归对 OKX 返回假 IP），表现为 **TCP 443 超时**、TLS 失败。  
  **处理**：在 Clash/mihomo 的 `dns.nameserver-policy` 中为 `+.okx.com` / `+.okex.com` 指定 **1.1.1.1**（或 DoH），并在 `fake-ip-filter` 中包含上述域名；仓库内 **`scripts/production_network_baseline.py --apply`** 可对 `/etc/clash/config.yaml` 做基线合并（**需 root + 重启 clash**）。  
- **`198.18.0.0/15`（fake-ip）**：若 OKX 仍解析进该段且连接失败，说明 **fake-ip 与路由/规则不一致**；优先保证 `fake-ip-filter` 含 `+.okx.com`，或在 `rules` 中对 OKX 使用 **DIRECT/REAL-IP** 与真实出口一致。  
- **自检**：`python3 scripts/network_connectivity_smoke.py` 会在异常解析时打印 `[HINT]`；探针未设置 `OPENCLAW_HTTP_PROXY` 时走**直连 DNS**，与「仅 TUN、未注入环境变量」的 shell 可能不一致，应以**交易进程实际环境**为准。  
- **A/B：`fake-ip-filter` / DNS 模块**：可用 **`scripts/clash_dns_fake_ip_filter_experiment.py`**（`show` / `backup` / `strip-okx` / `strip-all-filter` / `disable-dns` / `enable-dns` / `set-enhanced-mode <fake-ip|redir-host|normal>` / `restore`）在备份后临时改动，重启 Clash 再跑 smoke 对比。  
  **注意**：`argparse` 要求 **`--config` 写在子命令前面**，例如 `sudo python3 scripts/clash_dns_fake_ip_filter_experiment.py --config /etc/clash/config.yaml strip-okx`；写成 `strip-okx --config ...` 会落到默认路径并报错。  
  **A/B 对比**：每轮改 Clash 后执行 `python3 scripts/network_connectivity_smoke.py --https-okx`（必要时保存终端输出）即可对照 DNS/TCP/HTTPS 结果。

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

开启 TUN 前后、或调整本机代理环境前后，用同一脚本各跑一次并 `--compare` 两次 JSON，可看 **DNS/TCP/HTTPS 中位数延迟** 与 **是否仍依赖 HTTP 代理更快**。详见 **`docs/OPERATIONS.md`** §3.6 与仓库 **`scripts/proxy_mode_network_benchmark.py`**。
