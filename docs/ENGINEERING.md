# OpenClaw Trading — 工程文档

本文档描述**当前仓库**的运行架构、配置模型与模块边界；运维与网络见 [OPERATIONS.md](./OPERATIONS.md)，开发流程见 [DEVELOPMENT.md](./DEVELOPMENT.md)。

---

## 1. 运行时架构

| 组件 | 路径 / 说明 |
|------|-------------|
| 进程入口 | `src/main.py` → `TradingSystem`：初始化 `ConfigManager` → `MainController` → `APIServer`（FastAPI），先起 API 再跑主循环 |
| HTTP API | `src/modules/api/server.py`（容器内监听 `0.0.0.0:8000` 以便端口映射） |
| 主控制器 | `src/modules/main_controller.py`：装配交易所、风控、记忆、AI 引擎等 |
| 配置 | `src/modules/core/config_manager.py` |

高层关系：`main.py` 持有全局 `ConfigManager` 实例；各业务模块通过构造函数或 setter 获得 `config_manager`，使用 `await get_config(section, key)` 读取合并后的配置。

---

## 2. 配置模型（单一主文件）

### 2.1 文件

- **主业务配置（必选）**：仓库根目录 `config/config.yaml`（或 `config.yml`）。
- **本机覆盖（可选，勿提交 Git）**：同目录 `local.yaml` / `local.yml` / `local.json`。模板见 `config/config.local.example.yaml`。
- **密钥**：根目录 `.env`；运行时可用 `OPENCLAW__段__键__嵌套` 形式覆盖 YAML（亦支持已弃用前缀 `TRADING_`，会打日志提醒迁移）。

### 2.2 加载顺序

`ConfigManager` 在**未**指定 `config_dir` 时，会扫描所有存在的目录（见 `DEFAULT_CONFIG_PATHS`），对每个目录依次加载：

1. 该目录下的 **`config.yaml`** 或 **`config.yml`**（二选一，yaml 优先文件名）。
2. 该目录下的 **`local.*`**（按固定文件名列表）。

多个目录时按 `DEFAULT_CONFIG_PATHS` **顺序**合并；同一 key **后者覆盖前者**。默认顺序为：

`data/config` → `config` → `/app/data/config` → `/app/config`

**建议**：业务主 YAML **只维护一份**在 `config/config.yaml`；`data/config` 仅保留空目录或本机 `local.*`，避免再放第二份 `config.yaml` 造成混淆。

### 2.3 非 ConfigManager 的 YAML

`config/` 下 **`clash_config.yaml`、`subscription.yaml`、`data_sources.yaml`** 等由**独立脚本或模块**读取，**不会**被 `ConfigManager` 自动合并进主配置。

### 2.4 已移除的旧形态

以下已从仓库流程中移除，请勿再依赖：

- 根目录 `openclaw-trading.json` 及旧备份 / clobber 文件  
- `data/config/default.yml`、分散的 `*.json` 业务片段（旧式按文件分节）  
- `openclaw.yml` / `default.yml` / `production.yml` 多文件叠加载  

遗留 **Flask** 小工具 `src/web/app.py`：`GET /config` 仅**只读**返回 `config.yaml`（+ `local.*`）合并视图；`POST /config` 已返回 **410**，请直接改磁盘上的 YAML。

---

## 3. Docker 与卷

根目录 `docker-compose.yml`（若存在）典型约定：

- `./config` → `/app/config`：保证容器内与宿主机主配置一致。  
- `./src` → `/app/src`：开发时改代码可 `restart` 生效。  
- `./scripts` → `/app/scripts`（只读）：容器内可跑 `startup_acceptance.py`、网络基线等；宿主机全栈巡检见 `scripts/verify_full_stack_network.sh`。  
- `./tests` → `/app/tests`（只读）：便于在容器内对齐本机测试树。  
- `./data`、`./logs`、`./workspace`、`./backups`：持久化与产物。

镜像构建见 `Dockerfile`；启动命令 `start_production.sh` → `python3 src/main.py`。宿主机经 Clash 出站与容器代理约定见 `deploy/HOST_CLASH_EGRESS.md`。

---

## 4. 模块索引（摘要）

| 领域 | 代表路径 |
|------|-----------|
| 配置 / 校验 | `src/modules/core/config_manager.py`，`config_runtime_validate.py` |
| 主控 / 生命周期 | `src/modules/main_controller.py` |
| API / WebSocket | `src/modules/api/server.py` |
| 交易所 | `src/modules/exchanges/` |
| 记忆 | `src/modules/memory/` |
| 风控 / SLTP | `src/modules/core/risk_manager.py`，`stop_loss_take_profit.py` |
| LLM | `src/modules/core/enhanced_llm_manager.py` 等 |

OpenAPI 以运行实例 **`/openapi.json`** 为准。

---

## 5. 与 ARCHITECTURE 的关系

根目录 [ARCHITECTURE.md](../ARCHITECTURE.md) 仅保留跳转；**本文件**为工程细节的主入口。

---

*文档版本与仓库当前行为同步；若行为变更请更新 [CHANGELOG.md](./CHANGELOG.md)。*
