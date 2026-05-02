# AI 维护交接：2026 Q2 系统测试、优化结果固化与验证方法

本文档面向**后续接手的 AI / 工程同学**，固化本轮「全链路测试 → 问题定位 → 代码/配置优化 → 验证」的**结果**与**可重复方法**。  
详细门控参数释义仍以 [**TRADING_TUNING_GUIDE.md**](./TRADING_TUNING_GUIDE.md) 为准；排障路径见 [**TRADING_DEBUG_PLAYBOOK.md**](./TRADING_DEBUG_PLAYBOOK.md)；运维基线见 [**OPERATIONS.md**](./OPERATIONS.md)。

---

## 1. 本轮固化范围（摘要）

| 类别 | 说明 |
|------|------|
| **决策可观测性** | `DecisionTraceStore` 磁盘持久化（重启不丢样本）、`analyze_recent` 增加 `top_hold_reason_tags` |
| **执行前取价** | `ai_core`：交易所 ticker 失败时用 MI 缓存价 / `entry_price` 等多级兜底；symbol 变体遍历 |
| **TLS（OKX）** | 支持合并 `OPENCLAW_SSL_CA_BUNDLE`、标准 env CA、`OPENCLAW_OKX_INSECURE_SSL` 应急档 |
| **LLM** | 默认可调超时、`OPENCLAW_LLM_REQUEST_TIMEOUT_SEC` 覆盖 |
| **诊断语义** | `ai_core.get_status()` 增加 `trade_counters`，避免误读 `total_trades` |
| **第三方采集** | 全局最小请求间隔默认值收紧（仍可用 env 覆盖） |
| **事件库** | `scripts/prune_events_db.py` 运维脚本；生产曾对 `data/events.db` 按保留天数删除并 `VACUUM` |
| **环境模板** | `.env.example` 补充 TLS / LLM / 轨迹相关变量说明 |

---

## 2. 关键代码与路径索引

| 能力 | 路径 |
|------|------|
| 决策轨迹存储 | `src/modules/core/decision_trace_store.py`（默认持久化：`{repo}/data/runtime/decision_trace_store.json`，锚定仓库根目录） |
| AI 核心决策 / 取价兜底 | `src/modules/core/ai_core_decision_engine.py` |
| OKX TLS | `src/modules/exchanges/okx.py`：`/_build_ssl_context`、`/_okx_ssl_cafile_path`（模块级合并 CA） |
| LLM 客户端超时 | `src/modules/core/enhanced_llm_manager.py`：`BaseLLMProvider._build_httpx_client` |
| 第三方 HTTP 限速 | `src/modules/data/third_party_data_integrator.py`：`OPENCLAW_THIRD_PARTY_MIN_INTERVAL_SEC` |
| 司令台诊断 / 门控 API | `src/modules/api/module_control_api.py`：`trading-diagnosis`、`/modules/ai/guards` |

---

## 3. 环境变量（交接一览）

以下与本轮优化直接相关；完整密钥与代理仍以根目录 **`.env`** 为准（勿提交 Git）。

| 变量 | 作用 |
|------|------|
| `OPENCLAW_LLM_REQUEST_TIMEOUT_SEC` | LLM HTTP 总超时（秒），覆盖模型默认 |
| `OPENCLAW_DECISION_TRACE_PERSIST` | `1` 启用轨迹 JSON 落盘（默认建议启用） |
| `OPENCLAW_DECISION_TRACE_STORE_JSON` | 可选，自定义轨迹 JSON 绝对路径 |
| `OPENCLAW_THIRD_PARTY_MIN_INTERVAL_SEC` | 第三方源全局最小请求间隔 |
| `OPENCLAW_OKX_TIMEOUT_TOTAL` / `_CONNECT` / `_SOCK_READ` | OKX REST 超时与读取 |
| `SSL_CERT_FILE` | 显式系统 CA 包（如 Debian：`/etc/ssl/certs/ca-certificates.crt`） |
| `OPENCLAW_SSL_CA_BUNDLE` | **额外** PEM，与 certifi **合并**后再校验（HTTPS 代理 MITM 根证书） |
| `OPENCLAW_OKX_INSECURE_SSL` | `1` 关闭 TLS 校验（仅排障/受信环境） |

---

## 4. 验证与测试方法（推荐固定顺序）

### 4.1 进程与端口

```bash
ss -ltnp | grep ':8000'
curl -sS --max-time 10 'http://127.0.0.1:8000/api/v1/system/health'
```

期望：`data.status` 为 `healthy`。

### 4.2 全链路体检（司令台）

```bash
curl -sS --max-time 60 'http://127.0.0.1:8000/api/v1/modules/commander/trading-diagnosis' | jq '.data | keys'
```

重点字段：

- `data.ai_core`：含 `trade_counters`（`session_ring_records`、`unified_history_cache_records`、`position_symbols_tracked`）。  
  **说明**：历史字段 `total_trades` 表示 **ai_core 内存环形记录条数**，不是交易所终身成交笔数。
- `data.execution_gateway`：`policy_metrics`、`reconciliation`；重启后短期内 `last_order_*` 可能为空，直至下一笔经网关的下单。
- `data.analysis_pipeline_assessment`：数据质量与决策结果健康度摘要。

### 4.2b PnL 健康与门控热更新（OpenAPI 一致示例）

以下与 `module_control_api` 中路由定义一致：`APIRouter(prefix="/api/v1/modules")` + `commander/trading-diagnosis`、`ai/guards`。

```bash
BASE=http://127.0.0.1:8000   # 按部署修改主机/端口

# PnL 健康（司令台诊断子树）
curl -sS "${BASE}/api/v1/modules/commander/trading-diagnosis" | \
  jq '.data.ai_core.execution_guards.adaptive_profile.pnl_health'

# 无 jq 时：
curl -sS "${BASE}/api/v1/modules/commander/trading-diagnosis" | python3 -c \
  "import json,sys;d=json.load(sys.stdin);ai=(d.get('data')or{}).get('ai_core')or{};eg=ai.get('execution_guards')or{};ap=eg.get('adaptive_profile')or{};print(json.dumps(ap.get('pnl_health'),indent=2))"
```

**`pnl_health.expectancy` 语义**：该字段为近期平仓记录在 `ai_core` 内存环中的 **`decision.pnl` 算术平均值（USDT 绝对盈亏）**；字段名沿用 `expectancy`，**不要**按「每笔收益率」去误读成百分比。`max_drawdown` 与门限比对用于 `health=bad`；深入分析时请交叉 **`data/trade_history/trades.jsonl`** 与交易所对账。

```bash
# 读取当前门控与自适应档位（热更新前必做）
curl -sS "${BASE}/api/v1/modules/ai/guards" | \
  jq '{success, frequency_profile, adaptive_profile, sample_config_keys: (.config | keys | .[0:12])}'

# 热更新：POST 体为顶层扁平 JSON，键须在 update_ai_execution_guards 的 allowed 白名单内
curl -sS -X POST "${BASE}/api/v1/modules/ai/guards" \
  -H 'Content-Type: application/json' \
  -d '{"hold_avoidance_override_min_abs_sentiment": 0.02, "ai_autonomy_min_conf_floor": 0.50}' | \
  jq '{success, applied, message}'

# 路由自检：curl -sS "${BASE}/openapi.json" | grep -F 'ai/guards'
```

**警示**：`ai_autonomy_min_conf_floor` 若设得过低（例如 `0.15`），相对默认约 `0.52` 会显著抬高开仓面；应小步调整并在 **`decision-traces`** 中观察 `open_ratio` / 拒单占比。

### 4.3 拒单与 hold 标签（轨迹）

```bash
curl -sS --max-time 20 'http://127.0.0.1:8000/api/v1/modules/commander/decision-traces?limit=200' | jq '.data | {summary, top_guard_reasons, top_hold_reason_tags, recent: (.recent|length)}'
```

- `top_guard_reasons`：门控拒绝原因 Top。
- `top_hold_reason_tags`：结构化 hold 标签（如 `neutral_market`、`mtf_conflict`、`low_confidence`），用于**定向调参**，避免只看笼统 `hold_by_ai_decision`。

轨迹文件（可选核对磁盘）：

```bash
ls -la data/runtime/decision_trace_store.json
```

### 4.4 自动化单元测试（回归）

在项目根目录、已激活 `.venv`：

```bash
.venv/bin/python -m pytest tests/unit/test_execution_gateway.py tests/unit/test_decision_engine.py -q
```

扩展全量：`tests/unit/` 或 CI 等价命令见 `docs/DEVELOPMENT.md`。

### 4.5 日志抽检（人工 / AI）

```bash
grep -E 'ERROR|SSL|price_unavailable|价格兜底|hold_by_ai_decision' logs/runtime_manual_restart.log | tail -50
```

---

## 5. 调参方法论（给接手 AI 的操作约束）

1. **单一变量 / 小步**：每次只改一类门控或一组相关阈值；改动幅度用「小 delta」，记录前后窗口。
2. **验证窗口**：线上观察建议 **30～60 分钟**（或约定样本量），结合 `decision-traces` 的占比变化，而非单次成交。
3. **生效路径**：  
   - 静态：`config/config.yaml` + `data/config/local.json`（或 `local.yaml`）。  
   - 热更新：优先 **`POST /api/v1/modules/ai/guards`**，请求体为**扁平 JSON**（不要用 `{ "config": { ... } }` 外层包裹）；允许多数字段见实现中的 `allowed` 集合。**可复制命令与 `BASE` 写法见 §4.2b。**  
   - 持久化：确认接口会把关键项写入 `ConfigManager`/本地配置，避免仅内存生效后被刷新覆盖。
4. **归因顺序**：先看 **`price_unavailable` / `ticker_empty` / `klines_missing`**（数据通路），再看 **`hold_by_ai_decision` + `top_hold_reason_tags`**（策略与 AI），最后看执行网关与对账。
5. **回滚**：保留上一份门控快照；若 `open_ratio` 恶化或异常拒单飙升，按快照恢复。

更细的参数清单与场景说明：[**TRADING_TUNING_GUIDE.md**](./TRADING_TUNING_GUIDE.md)。

---

## 6. 运维操作（events.db 与重启）

### 6.1 `data/events.db` 裁剪

脚本：`scripts/prune_events_db.py`

- **务必在维护窗口或停服务后执行**，否则易出现 `database is locked`（事件系统占用 SQLite）。
- 示例：

```bash
# 在仓库根目录 ai-trading-system；停交易进程后再执行，避免 database is locked
cd /path/to/ai-trading-system
.venv/bin/python scripts/prune_events_db.py --db data/events.db --keep-days 30 --vacuum
```

- `--keep-days`：保留「当前时间往前 N 天内」的事件；越早的数据越早被删。
- `--vacuum`：回收空间（大库可能耗时数分钟）。

### 6.2 进程锁与重启

单实例锁：`ProcessLock("openclaw-trading")`，锁文件常见 `/tmp/openclaw-trading.lock`。  
若异常退出残留锁，需在确认无旧进程后清理再启动：

```bash
pkill -f '\.venv/bin/python -m src.main' || true
sleep 2
rm -f /tmp/openclaw-trading.lock /tmp/openclaw-trading.pid
cd /path/to/ai-trading-system && nohup env PYTHONUNBUFFERED=1 .venv/bin/python -m src.main >> logs/runtime_manual_restart.log 2>&1 &
```

根目录 **`main.py` 会通过 `load_dotenv` 加载 `.env`**，一般无需在 shell 手动 `source .env`。

---

## 7. 已知边界与后续可选优化

| 项 | 说明 |
|----|------|
| **events.db 体积** | 高频事件写入时仍会增长；除 prune 外，可考虑降低部分事件类型的持久化频率（需单独评审）。 |
| **mihomo 未配置 MITM** | 若无独立代理根证书，仅依赖系统 CA；若仍报 SSL，再配置 `OPENCLAW_SSL_CA_BUNDLE`。 |
| **诊断字段语义** | `execution_gateway.last_order_*` 在重启后可能为空直至下一笔订单；属正常现象。 |
| **策略层 hold** | `top_hold_reason_tags` 反映 AI/规则倾向；调阈值与提示词属于产品决策，需与风控目标一致。 |

---

## 8. 文档关系（勿重复造轮子）

| 文档 | 用途 |
|------|------|
| [TRADING_TUNING_GUIDE.md](./TRADING_TUNING_GUIDE.md) | 门控参数权威说明 |
| [TRADING_DEBUG_PLAYBOOK.md](./TRADING_DEBUG_PLAYBOOK.md) | 开平仓排障步骤 |
| [OPERATIONS.md](./OPERATIONS.md) | 部署、网络、健康巡检 |
| [API_REFERENCE.md](./API_REFERENCE.md) | REST 契约 |

---

## 9. 变更追溯

- 本文档对应仓库 **`docs/AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md`**，与 **`CHANGELOG.md`** 中同期条目可交叉引用（若团队要求在大变更时追加 CHANGELOG 条目，请同步维护）。
