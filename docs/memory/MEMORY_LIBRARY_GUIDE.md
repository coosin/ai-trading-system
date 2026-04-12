# MemoryGateway — 运维与配置要点

与主系统配置模型一致：**记忆相关可调参数**写在 **`config/config.yaml` 的 `memory:` 段**；本机差异用同目录 **`local.yaml`**（勿提交）。

## 1. 配置来源

- `ConfigManager` **只自动合并**各配置目录下的 **`config.yaml` + `local.*`**。  
- 不会在后台自动扫描 `data/config/memory.json` 等零散文件名；若历史文档提到独立 JSON，请迁移到 **`memory:` YAML 段** 或 `local.json` 中的 `"memory": { ... }`。

## 2. 环境变量

仍可使用 `OPENCLAW__memory__...` 覆盖文件中的值（适合临时调参与密钥类项）。

## 3. 运行时数据

结构化记忆与治理文本通常落在 `data/memory/`、`workspace/` 下；升级前请按需备份。

## 4. API 与可观测

以运行中 OpenAPI（`/docs`）为准；常见只读端点包括质量与统计类路由（若当前版本已启用）。

---

更完整的 API 与字段说明见项目根 OpenAPI 与 [ENGINEERING.md](../ENGINEERING.md)。
