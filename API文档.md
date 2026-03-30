# 全智能量化交易系统 API 文档

## 1. 系统概览

全智能量化交易系统提供了完整的RESTful API接口，用于管理交易策略、监控系统状态、执行交易操作等。系统采用模块化设计，支持多交易所、多策略、实时监控和风险管理。

## 2. 接口目录

### 2.1 系统管理
- **GET /health** - 健康检查
- **GET /metrics** - 获取系统指标

### 2.2 认证管理
- **POST /auth/login** - 用户登录

### 2.3 策略管理
- **GET /api/strategies/list** - 获取策略列表
- **GET /api/strategies/performance** - 获取策略性能
- **POST /api/strategies/activate/{strategy_name}** - 激活策略
- **POST /api/strategies/deactivate/{strategy_name}** - 停用策略
- **POST /api/strategies/update/{strategy_name}** - 更新策略参数
- **POST /api/strategies/add** - 添加策略
- **DELETE /api/strategies/remove/{strategy_name}** - 移除策略

### 2.4 监控管理
- **GET /api/monitoring/status** - 获取系统状态
- **GET /api/monitoring/trades** - 获取交易历史
- **GET /api/monitoring/risk** - 获取风险指标
- **GET /api/monitoring/alerts** - 获取告警信息

### 2.5 回测管理
- **POST /api/backtest/run** - 运行回测
- **GET /api/backtest/results** - 获取回测结果
- **POST /api/backtest/optimize** - 优化策略参数

### 2.6 风险管理
- **GET /api/risk/portfolio** - 获取投资组合信息
- **GET /api/risk/metrics** - 获取风险指标
- **POST /api/risk/adjust** - 调整风险参数

## 3. 详细接口说明

### 3.1 策略管理接口

#### GET /api/strategies/list
- **功能**：获取所有策略信息
- **参数**：无
- **返回**：
  ```json
  {
    "strategies": ["MovingAverageStrategy", "RSIStrategy"],
    "active_strategies": ["MovingAverageStrategy"],
    "best_strategy": "MovingAverageStrategy"
  }
  ```

#### GET /api/strategies/performance
- **功能**：获取策略性能指标
- **参数**：无
- **返回**：
  ```json
  {
    "MovingAverageStrategy": {
      "total_pnl": 1250.50,
      "win_rate": 0.65,
      "sharpe_ratio": 1.25,
      "max_drawdown": 0.08,
      "trade_count": 25
    },
    "RSIStrategy": {
      "total_pnl": 980.25,
      "win_rate": 0.60,
      "sharpe_ratio": 1.10,
      "max_drawdown": 0.10,
      "trade_count": 20
    }
  }
  ```

#### POST /api/strategies/activate/{strategy_name}
- **功能**：激活指定策略
- **参数**：
  - `strategy_name`：策略名称（路径参数）
- **返回**：
  ```json
  {
    "status": "success",
    "message": "策略 MovingAverageStrategy 已激活"
  }
  ```

#### POST /api/strategies/deactivate/{strategy_name}
- **功能**：停用指定策略
- **参数**：
  - `strategy_name`：策略名称（路径参数）
- **返回**：
  ```json
  {
    "status": "success",
    "message": "策略 MovingAverageStrategy 已停用"
  }
  ```

#### POST /api/strategies/update/{strategy_name}
- **功能**：更新策略参数
- **参数**：
  - `strategy_name`：策略名称（路径参数）
  - 请求体：
    ```json
    {
      "short_window": 15,
      "long_window": 45
    }
    ```
- **返回**：
  ```json
  {
    "status": "success",
    "message": "策略 MovingAverageStrategy 参数已更新"
  }
  ```

#### POST /api/strategies/add
- **功能**：添加新策略
- **参数**：
  - 请求体：
    ```json
    {
      "type": "moving_average",
      "name": "CustomMA Strategy",
      "short_window": 20,
      "long_window": 50,
      "symbol": "BTC/USDT"
    }
    ```
- **返回**：
  ```json
  {
    "status": "success",
    "message": "策略 CustomMA Strategy 已添加"
  }
  ```

#### DELETE /api/strategies/remove/{strategy_name}
- **功能**：移除指定策略
- **参数**：
  - `strategy_name`：策略名称（路径参数）
- **返回**：
  ```json
  {
    "status": "success",
    "message": "策略 CustomMA Strategy 已移除"
  }
  ```

### 3.2 监控管理接口

#### GET /api/monitoring/status
- **功能**：获取系统状态
- **参数**：无
- **返回**：
  ```json
  {
    "system_status": "running",
    "module_statuses": {
      "data_pipeline": "running",
      "trade_engine": "running",
      "risk_manager": "running"
    },
    "metrics": {
      "total_events": 1500,
      "total_errors": 5,
      "module_starts": 10
    }
  }
  ```

#### GET /api/monitoring/trades
- **功能**：获取交易历史
- **参数**：无
- **返回**：
  ```json
  {
    "trades": [
      {
        "id": "1",
        "symbol": "BTC/USDT",
        "side": "buy",
        "price": 50000.0,
        "quantity": 0.1,
        "timestamp": "2023-10-01T10:00:00Z"
      }
    ]
  }
  ```

### 3.3 回测管理接口

#### POST /api/backtest/run
- **功能**：运行回测
- **参数**：
  - 请求体：
    ```json
    {
      "strategy": "MovingAverageStrategy",
      "symbol": "BTC/USDT",
      "start_date": "2023-01-01",
      "end_date": "2023-06-01",
      "parameters": {
        "short_window": 20,
        "long_window": 50
      }
    }
    ```
- **返回**：
  ```json
  {
    "backtest_id": "bt-12345",
    "status": "running"
  }
  ```

### 3.4 风险管理接口

#### GET /api/risk/portfolio
- **功能**：获取投资组合信息
- **参数**：无
- **返回**：
  ```json
  {
    "total_equity": 100000.0,
    "available_balance": 30000.0,
    "margin_used": 70000.0,
    "leverage": 2.5,
    "positions": [
      {
        "symbol": "BTC/USDT",
        "side": "long",
        "quantity": 1.0,
        "entry_price": 50000.0,
        "current_price": 52000.0,
        "pnl": 2000.0
      }
    ]
  }
  ```

## 4. 认证方式

系统采用JWT（JSON Web Token）进行认证。用户登录后获取token，然后在后续请求中通过Authorization头传递token。

### 登录示例
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### 带认证的请求示例
```bash
curl -X GET http://localhost:8000/api/strategies/list \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 5. 错误处理

API返回的错误格式统一为：

```json
{
  "status": "error",
  "error": "错误信息",
  "timestamp": "2023-10-01T10:00:00Z"
}
```

常见错误码：
- 400：请求参数错误
- 401：未授权
- 404：资源不存在
- 500：服务器内部错误

## 6. WebSocket接口

系统提供WebSocket接口用于实时数据推送：

### 连接地址
```
ws://localhost:8000/ws
```

### 订阅频道
```json
{
  "type": "subscribe",
  "channels": ["market_data", "trades", "alerts"]
}
```

### 接收消息示例
```json
{
  "type": "data",
  "channel": "market_data",
  "data": {
    "symbol": "BTC/USDT",
    "price": 50000.0,
    "volume": 1000.0,
    "timestamp": "2023-10-01T10:00:00Z"
  },
  "timestamp": "2023-10-01T10:00:00Z"
}
```

## 7. 使用示例

### 7.1 Python SDK示例

```python
import requests
import json

# 登录获取token
response = requests.post('http://localhost:8000/auth/login', json={
    'username': 'admin',
    'password': 'admin123'
})
token = response.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# 获取策略列表
response = requests.get('http://localhost:8000/api/strategies/list', headers=headers)
print('策略列表:', response.json())

# 运行回测
backtest_data = {
    'strategy': 'MovingAverageStrategy',
    'symbol': 'BTC/USDT',
    'start_date': '2023-01-01',
    'end_date': '2023-06-01',
    'parameters': {
        'short_window': 20,
        'long_window': 50
    }
}
response = requests.post('http://localhost:8000/api/backtest/run', json=backtest_data, headers=headers)
print('回测结果:', response.json())
```

### 7.2 命令行示例

```bash
# 获取系统状态
curl http://localhost:8000/health

# 登录
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' \
  | jq -r '.access_token')

# 获取策略性能
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/strategies/performance

# 激活策略
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/strategies/activate/MovingAverageStrategy
```

## 8. 部署说明

### 8.1 本地开发

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 启动系统：
   ```bash
   python src/main.py
   ```

3. 访问API文档：
   ```
   http://localhost:8000/docs
   ```

### 8.2 Docker部署

1. 构建镜像：
   ```bash
   docker build -t trading-system .
   ```

2. 运行容器：
   ```bash
   docker run -p 8000:8000 trading-system
   ```

## 9. 注意事项

1. **安全**：生产环境中应修改默认密码，限制API访问权限。
2. **性能**：对于高频交易，建议使用WebSocket接口获取实时数据。
3. **监控**：定期检查系统状态和风险指标，确保系统正常运行。
4. **备份**：定期备份策略配置和交易数据。

## 10. 版本历史

- v1.0.0：初始版本，包含基本交易功能
- v1.1.0：添加多策略支持和自动切换机制
- v1.2.0：增强风险管理和监控功能
- v1.3.0：添加回测系统和策略优化功能