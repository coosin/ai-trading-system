# TOOLS.md - 交易系统工具配置

## API密钥管理
⚠️ **重要**：永远不要硬编码API密钥在脚本中！

### 推荐的安全实践
```bash
# 使用环境变量
export BINANCE_API_KEY="your_api_key"
export BINANCE_SECRET_KEY="your_secret_key"
export OKX_API_KEY="your_okx_key"
export OKX_SECRET_KEY="your_okx_secret"
export OKX_PASSPHRASE="your_passphrase"

# 或使用加密配置文件
# 存储在 ~/.openclaw/workspace-trading/crypto-config/encrypted_keys.asc
```

## 交易所API端点
### Binance
- 现货交易API：`https://api.binance.com`
- WebSocket行情：`wss://stream.binance.com:9443/ws`
- 测试网络：`https://testnet.binance.vision`

### OKX
- REST API：`https://www.okx.com`
- WebSocket：`wss://ws.okx.com:8443/ws/v5/public`
- 模拟交易：`https://www.okx.com/priapi/v5/demo`

## 常用Python库
```bash
# 交易库
pip install ccxt pandas numpy ta-lib

# 数据可视化
pip install matplotlib plotly

# 异步处理
pip install aiohttp asyncio

# 机器学习（可选）
pip install scikit-learn tensorflow
```

## 交易脚本位置
- `scripts/trading/` - 核心交易策略
- `scripts/monitoring/` - 市场监控
- `scripts/analysis/` - 数据分析
- `scripts/backtesting/` - 回测系统

## 数据库配置
### SQLite（简单）
```python
# 交易记录数据库
db_path = "/home/cool/.openclaw/workspace-trading/database/trading.db"
```

### PostgreSQL（生产环境）
```
host: localhost
port: 5432
database: crypto_trading
user: trading_bot
password: [环境变量]
```

## 监控工具
### 系统监控
- **进程管理**：使用systemd或supervisor
- **日志收集**：ELK Stack或Loki+Grafana
- **性能监控**：Prometheus + Grafana

### 交易监控
- **价格预警**：自定义价格触发器
- **仓位监控**：实时持仓和价值计算
- **风险监控**：VaR计算和压力测试

## 备份策略
### 自动备份脚本
```bash
#!/bin/bash
# scripts/backup/auto_backup.sh
# 每日凌晨3点执行
0 3 * * * /home/cool/.openclaw/workspace-trading/scripts/backup/auto_backup.sh
```

### 备份内容
1. 交易记录数据库
2. 配置文件（加密）
3. 策略参数
4. 绩效报告

## 紧急恢复
### 灾难恢复脚本
```bash
# scripts/recovery/emergency_recovery.sh
# 系统异常时执行
```

### 恢复步骤
1. 停止所有交易进程
2. 备份当前状态
3. 恢复最近的有效备份
4. 验证系统完整性
5. 逐步恢复交易功能