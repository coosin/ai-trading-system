# Scripts Inventory

这个目录不能继续当“临时分析垃圾桶”用。标准入口已经收敛到 `/api/v1/{domain}/...`，脚本只保留三类：

1. 运行必需：启动、停止、健康检查、验收。
2. 运维辅助：网络、代理、对账、回填。
3. 人工分析：只读报表，但应优先迁到现有 API/UI，而不是无限增长。

新增规则：

- 新脚本只有在以下条件至少满足一项时才允许存在：
  - 被 `verify.py` / 定时任务 / systemd / 运维文档直接调用
  - 明确作为一次性迁移工具，并在完成后删除
  - 短期过渡，但已经有迁入 API/UI 的计划
- 纯分析需求优先扩展标准 API：
  - `/api/v1/commander/system-mastery`
  - `/api/v1/strategy/overview`
  - `/api/v1/trades/lifecycle`
  - `/api/v1/agents/effectiveness`
  - `/api/v1/surface/registry`
- 未接 UI、未接自动化、未接文档流程的脚本，默认视为候选清理对象。

## API base URL

调用 HTTP API 的脚本统一读取 `OPENCLAW_API_BASE`，其次兼容 `ACCEPTANCE_BASE`、`BASE_URL`。规范见 `docs/API_REFERENCE.md` 和 `docs/OPERATIONS.md`。

## A. 运行必需

- `verify.py`
  - 统一验收入口。
- `trading_exec_fullcheck.py`
  - 交易闭环验收。
- `startup_acceptance.py`
  - 启动验收。
- `full_system_audit.py`
  - 单次全系统审计。
- `live_stability_monitor.py`
  - 持续稳定性监控。
- `health_suite_summary.py`
  - 汇总健康检查结果。
- `health_suite_status.py`
  - 输出自动化可消费状态。
- `run_scheduled_health_suite.sh`
  - 定时运行健康检查套件。
- `start-openclaw-trading.sh`
  - 启动服务。
- `stop-openclaw-trading.sh`
  - 停止服务。
- `check_trading_host_health.sh`
  - 宿主机健康检查。
- `openclaw_auth_selfcheck.sh`
  - 认证自检。

## B. 运维辅助

- `network_connectivity_smoke.py`
- `production_network_baseline.py`
- `proxy_mode_network_benchmark.py`
- `okx_proxy_guard.py`
- `verify_full_stack_network.sh`
- `cleanup_trading_workspace.sh`
- `prune_events_db.py`
- `backfill_trade_truth_from_exchange.py`
- `migrate_strategy_ids.py`
- `reconcile_report_triage.py`

这些脚本可以保留，但必须服务于网络、对账、数据回填、清理，不承担核心交易分析入口角色。

## C. 人工分析脚本

人工分析脚本不再作为长期入口保留。历史脚本的核心输出已经统一迁到：

- `/api/v1/commander/system-mastery`
- `/api/v1/strategy/overview`
- `/api/v1/trades/lifecycle`
- `/api/v1/agents/effectiveness`
- 前端闭环复盘页面

## D. 调优/实验脚本

- `sltp_sr_simtest.py`
- `tuning/ai_proposal.py`
- `tuning/quality_eval.py`
- `tuning/tuning_channel.py`
- `clash_dns_fake_ip_filter_experiment.py`
- `commander_dispatch_client.py`

这些脚本不是日常读盘入口。它们只应用于局部实验、离线评估或调优通道验证。

## E. 当前明确存在的问题

- 交易闭环复盘还没有统一前端页面。
- 多个分析脚本与现有 API 能力重复，已进入删除或迁移范围。
- `scripts/__pycache__` 不应作为仓库资产存在，已清理，不能再次提交。
- “开仓依据、拒单依据、后续走势跟踪、平仓早晚、收益归因、学习反馈”统一进入 `/api/v1/trades/lifecycle` 和 `/api/v1/commander/system-mastery`。

## F. 后续收口原则

- 不再新增临时分析脚本来回答日常优化问题。
- 日常复盘统一收口到现有 API，再由前端消费。
- 如果某个脚本的核心输出值得长期保留，就把它迁进 API/UI，然后删除脚本。
- 如果某个脚本既没被自动化使用，也不在迁移计划内，就进入清理名单。
