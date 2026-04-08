# 全智能量化交易系统 - API文档

## 概述

本文档描述了全智能量化交易系统的RESTful API接口。所有API端点都位于 `/api/v1` 路径下。

## 基础URL

```
http://localhost:8000/api/v1
```

## 认证

### JWT认证

大多数API端点需要JWT认证。获取token后，需要在请求头中包含：

```
Authorization: Bearer <your_token>
```

### API密钥认证

也可以使用API密钥进行认证：

```
X-API-Key: <your_api_key>
X-API-Secret: <your_api_secret>
```

## 通用响应格式

### 成功响应

```json
{
  "success": true,
  "data": {...},
  "message": "操作成功"
}
```

### 错误响应

```json
{
  "success": false,
  "error": "错误信息",
  "code": "ERROR_CODE"
}
```

## API端点

### 1. 认证接口

#### 1.1 用户登录

**POST** `/auth/login`

请求体：
```json
{
  "username": "admin",
  "password": "admin123"
}
```

响应：
```json
{
  "success": true,
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "user_id": "admin_001",
      "username": "admin",
      "email": "admin@example.com",
      "role": "admin"
    }
  }
}
```

#### 1.2 用户登出

**POST** `/auth/logout`

需要认证

#### 1.3 刷新令牌

**POST** `/auth/refresh`

需要认证

#### 1.4 获取当前用户信息

**GET** `/auth/me`

需要认证

响应：
```json
{
  "success": true,
  "data": {
    "user_id": "admin_001",
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

### 2. 系统状态接口

#### 2.1 获取系统状态

**GET** `/status`

需要认证

响应：
```json
{
  "success": true,
  "data": {
    "system_status": "running",
    "start_time": "2024-01-01T00:00:00Z",
    "uptime": 3600,
    "module_count": 15,
    "running_modules": 14,
    "module_statuses": {
      "event_system": "healthy",
      "database": "healthy",
      "strategy_manager": "healthy"
    },
    "metrics": {
      "total_events": 1000,
      "total_errors": 5
    }
  }
}
```

#### 2.2 健康检查

**GET** `/health`

无需认证

响应：
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

---

### 2.x 司令部（Commander）统一控制接口（modules）

司令部接口用于统一前端与消息通道（如 TG）的控制入口与状态快照。

#### 2.x.1 获取司令部快照

**GET** `/modules/commander/snapshot`

查询参数：
- `symbol`：默认 `BTC/USDT`
- `mode`：`fast|full`（默认 `fast`）

说明：
- `fast` 用于高频刷新，优先返回核心状态，避免重聚合阻塞。
- `full` 返回更完整但可能更慢的快照。

#### 2.x.2 触发司令部日常任务

**POST** `/modules/commander/chores`

请求体示例：
```json
{
  "symbol": "BTC/USDT",
  "trigger_optimize": false
}
```

#### 2.x.3 司令部统一指令入口

**POST** `/modules/commander/dispatch`

请求体示例：
```json
{
  "message": "执行系统巡检并汇总告警",
  "source": "telegram"
}
```

#### 2.x.4 司令部全链路审查

**GET** `/modules/commander/audit`

#### 2.3 获取系统指标

**GET** `/metrics`

需要认证

### 3. 策略管理接口

#### 3.1 获取所有策略

**GET** `/strategies`

需要认证

响应：
```json
{
  "success": true,
  "data": [
    {
      "id": "macd_001",
      "name": "MACD策略",
      "type": "macd",
      "is_active": true,
      "parameters": {
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9
      },
      "performance": {
        "total_return": 0.15,
        "sharpe_ratio": 1.8,
        "win_rate": 0.55
      },
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

#### 3.2 获取单个策略

**GET** `/strategies/{id}`

需要认证

#### 3.3 创建策略

**POST** `/strategies`

需要认证

请求体：
```json
{
  "name": "新策略",
  "type": "custom",
  "parameters": {...},
  "symbols": ["BTC/USDT"]
}
```

#### 3.4 更新策略

**PUT** `/strategies/{id}`

需要认证

#### 3.5 删除策略

**DELETE** `/strategies/{id}`

需要认证

#### 3.6 激活策略

**POST** `/strategies/{id}/activate`

需要认证

#### 3.7 停用策略

**POST** `/strategies/{id}/deactivate`

需要认证

#### 3.8 获取策略性能

**GET** `/strategies/{id}/performance`

需要认证

### 4. 交易接口

#### 4.1 获取持仓

**GET** `/trading/positions`

需要认证

响应：
```json
{
  "success": true,
  "data": [
    {
      "symbol": "BTC/USDT",
      "quantity": 0.1,
      "entry_price": 40000,
      "current_price": 42000,
      "unrealized_pnl": 200,
      "unrealized_pnl_percent": 0.05
    }
  ]
}
```

#### 4.2 获取订单

**GET** `/trading/orders`

需要认证

查询参数：
- `status`: 订单状态过滤
- `symbol`: 交易对过滤

#### 4.3 创建订单

**POST** `/trading/orders`

需要认证

请求体：
```json
{
  "symbol": "BTC/USDT",
  "side": "buy",
  "order_type": "limit",
  "quantity": 0.01,
  "price": 40000,
  "execution_algorithm": "simple"
}
```

#### 4.4 取消订单

**DELETE** `/trading/orders/{id}`

需要认证

#### 4.5 获取交易历史

**GET** `/trading/history`

需要认证

查询参数：
- `start_date`: 开始日期
- `end_date`: 结束日期
- `symbol`: 交易对过滤
- `limit`: 记录数量限制

### 5. 市场数据接口

#### 5.1 获取交易对列表

**GET** `/market/symbols`

需要认证

响应：
```json
{
  "success": true,
  "data": [
    {
      "symbol": "BTC/USDT",
      "base_currency": "BTC",
      "quote_currency": "USDT",
      "status": "trading"
    },
    {
      "symbol": "ETH/USDT",
      "base_currency": "ETH",
      "quote_currency": "USDT",
      "status": "trading"
    }
  ]
}
```

#### 5.2 获取Ticker数据

**GET** `/market/ticker/{symbol}`

需要认证

响应：
```json
{
  "success": true,
  "data": {
    "symbol": "BTC/USDT",
    "last_price": 42000,
    "bid": 41990,
    "ask": 42010,
    "high_24h": 43000,
    "low_24h": 40000,
    "volume_24h": 1000000,
    "change_24h": 0.05,
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

#### 5.3 获取K线数据

**GET** `/market/klines/{symbol}`

需要认证

查询参数：
- `interval`: 时间周期 (1m, 5m, 15m, 1h, 4h, 1d)
- `limit`: 数据点数量 (默认100)
- `start_time`: 开始时间 (可选)
- `end_time`: 结束时间 (可选)

响应：
```json
{
  "success": true,
  "data": [
    {
      "timestamp": "2024-01-01T00:00:00Z",
      "open": 40000,
      "high": 40500,
      "low": 39500,
      "close": 40200,
      "volume": 100
    }
  ]
}
```

#### 5.4 获取订单簿

**GET** `/market/orderbook/{symbol}`

需要认证

响应：
```json
{
  "success": true,
  "data": {
    "symbol": "BTC/USDT",
    "bids": [
      [41990, 0.5],
      [41980, 1.0],
      [41970, 0.3]
    ],
    "asks": [
      [42010, 0.4],
      [42020, 0.8],
      [42030, 0.2]
    ],
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

### 6. 风险管理接口

#### 6.1 获取风险概览

**GET** `/risk/overview`

需要认证

响应：
```json
{
  "success": true,
  "data": {
    "total_equity": 100000,
    "used_margin": 20000,
    "available_margin": 80000,
    "margin_level": 5.0,
    "total_pnl": 5000,
    "total_pnl_percent": 0.05,
    "open_positions": 3,
    "max_drawdown": 0.08,
    "var_95": 2000,
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

#### 6.2 获取VaR

**GET** `/risk/var`

需要认证

#### 6.3 获取最大回撤

**GET** `/risk/drawdown`

需要认证

#### 6.4 获取持仓限制

**GET** `/risk/limits`

需要认证

### 7. 回测接口

#### 7.1 运行回测

**POST** `/backtest/run`

需要认证

请求体：
```json
{
  "strategy_id": "macd_001",
  "symbol": "BTC/USDT",
  "start_date": "2024-01-01",
  "end_date": "2024-03-01",
  "initial_capital": 10000,
  "parameters": {...}
}
```

响应：
```json
{
  "success": true,
  "data": {
    "backtest_id": "bt_001",
    "status": "running"
  }
}
```

#### 7.2 获取回测结果

**GET** `/backtest/results/{id}`

需要认证

#### 7.3 获取回测历史

**GET** `/backtest/history`

需要认证

### 8. 监控接口

#### 8.1 获取告警

**GET** `/monitoring/alerts`

需要认证

#### 8.2 获取日志

**GET** `/monitoring/logs`

需要认证

查询参数：
- `level`: 日志级别 (debug, info, warning, error)
- `module`: 模块过滤
- `start_date`: 开始日期
- `end_date`: 结束日期
- `limit`: 记录数量限制

#### 8.3 获取性能监控

**GET** `/monitoring/performance`

需要认证

### 9. 自然语言接口

#### 9.1 自然语言查询

**POST** `/nlp/query`

需要认证

请求体：
```json
{
  "question": "今天BTC的趋势如何？"
}
```

响应：
```json
{
  "success": true,
  "data": {
    "answer": "根据当前市场数据分析，BTC今日呈现上升趋势...",
    "analysis": {...}
  }
}
```

## WebSocket接口

### 实时数据推送

**连接** `ws://localhost:8000/ws/market`

需要认证

消息格式：
```json
{
  "type": "ticker",
  "data": {
    "symbol": "BTC/USDT",
    "last_price": 42000,
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

订阅消息：
```json
{
  "action": "subscribe",
  "channels": ["ticker", "orderbook", "trades"],
  "symbols": ["BTC/USDT", "ETH/USDT"]
}
```

## 错误码

| 错误码 | 说明 |
|--------|------|
| UNAUTHORIZED | 未授权 |
| FORBIDDEN | 权限不足 |
| NOT_FOUND | 资源不存在 |
| VALIDATION_ERROR | 验证错误 |
| INTERNAL_ERROR | 内部错误 |
| STRATEGY_ERROR | 策略错误 |
| TRADING_ERROR | 交易错误 |
| EXCHANGE_ERROR | 交易所错误 |

## 速率限制

- 认证用户：1000请求/分钟
- API密钥：500请求/分钟
- 未认证：100请求/分钟

## 版本历史

- v2.0.0 (2024-03-30): 完整API文档
- v1.0.0 (2024-01-01): 初始版本
