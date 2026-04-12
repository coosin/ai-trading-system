# 变更记录

## 2026-04-13 — 文档与仓库卫生

- **文档**：`ENGINEERING` 补充 Compose 挂载 `./scripts`、`./tests` 与 `HOST_CLASH_EGRESS` 引用；`OPERATIONS` 补充 `verify_full_stack_network.sh`、`/api/v1/system/acceptance`、`startup_acceptance.py` 与宿主机 Clash 文档链接；`docs/README`、根 `README` 同步索引与快速命令。
- **仓库**：`agents/`（本地会话类 `*.jsonl` 等）不再纳入版本控制，已加入 `.gitignore` 并从索引移除历史误提交文件；`workspace/memory/working/` 等运行时碎片与 `data/**/*.db`、`backups/`、`logs` 下滚动日志与 `logs/config-health.json` 等写入 `.gitignore`，已跟踪的 `working/*.json` 从索引移除。

## 2026-04-12 — 配置统一与仓库清理

- **配置**：业务主配置仅为 `config/config.yaml`（及可选同目录 `local.*`）；`ConfigManager` 不再加载 `openclaw.yml`、`default.yml`、按节分散的旧 JSON 树。
- **删除**：根目录 `openclaw-trading.json*` 备份；`data/config` 下旧 `default.yml`、`*.json` 测试碎片等；该目录保留 `.gitkeep` 供可选本机 `local.*`。
- **Docker**：恢复/提供根目录 `docker-compose.yml`，默认 `MODE`/`TRADING_MODE`/`SYSTEM_MODE` 为 **simulation**（部署实盘前请在 `.env` 显式覆盖）；挂载 `./config:/app/config`。
- **测试**：Pytest 9 要求异步 fixture 使用 `pytest_asyncio.fixture`；`NaturalLanguageInterface` 单测改为 `IsolatedAsyncioTestCase`。
- **工具**：`src/web/app.py` 改为读取主 YAML；新增 `scripts/network_connectivity_smoke.py`。
- **文档**：补回 `docs/ENGINEERING.md`、`docs/CHANGELOG.md`、`docs/memory/MEMORY_LIBRARY_GUIDE.md`；更新 `OPERATIONS`、`DEVELOPMENT`、`README` 索引；`status.sh` / `check-dual-system.sh` 改为检查 `config/config.yaml`。
- **仓库**：新增根 `.gitignore`（含 `config/local.*`、`data/config/local.*` 等）。
