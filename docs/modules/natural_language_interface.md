# 自然语言接口 (NaturalLanguageInterface) 模块

## 概述

自然语言接口模块是全智能量化交易系统的智能交互组件，允许用户通过自然语言与系统进行交互。它利用大模型的能力，将用户的自然语言查询转换为系统命令，并将执行结果以自然语言的形式返回给用户。

## 核心功能

### 1. 命令识别

- 自动识别用户查询对应的系统命令
- 支持多种命令类型，如获取系统状态、分析市场、生成策略等
- 基于关键词和上下文理解，提高命令识别的准确性

### 2. 参数提取

- 从用户的自然语言查询中提取命令参数
- 支持复杂参数的提取和解析
- 自动处理参数的默认值和类型转换

### 3. 命令执行

- 执行识别到的系统命令
- 处理命令执行过程中的错误和异常
- 生成结构化的命令执行结果

### 4. 自然语言响应生成

- 将命令执行结果转换为自然、友好的自然语言响应
- 保持响应的一致性和专业性
- 适应不同用户的语言风格和偏好

### 5. 通用问答

- 处理不属于特定命令的通用查询
- 提供关于系统、策略、市场等方面的信息
- 基于大模型的知识和系统上下文提供准确的回答

## 类结构

```python
class NaturalLanguageInterface:
    def __init__(self, llm_integration):
        # 初始化自然语言接口
        
    async def process_query(self, query, context=None):
        # 处理自然语言查询
        
    async def _identify_command(self, query):
        # 识别查询对应的命令
        
    async def _execute_command(self, command, query, context=None):
        # 执行命令
        
    async def _extract_parameters(self, command, query, context=None):
        # 提取命令参数
        
    async def _general_qa(self, query, context=None):
        # 通用问答
        
    async def generate_response(self, result, query):
        # 生成自然语言响应
        
    async def process_and_respond(self, query, context=None):
        # 处理查询并生成响应
        
    def get_available_commands(self):
        # 获取可用命令
        
    def add_command(self, command_name, description, keywords, function):
        # 添加新命令
        
    def remove_command(self, command_name):
        # 删除命令
```

## 可用命令

| 命令名称 | 描述 | 关键词 |
|---------|------|--------|
| get_system_status | 获取系统状态 | 系统状态, 运行状态, 健康状态, 系统信息 |
| get_strategy_performance | 获取策略性能 | 策略性能, 策略表现, 收益情况, 策略统计 |
| analyze_market | 分析市场 | 市场分析, 行情分析, 市场趋势, 市场预测 |
| generate_strategy | 生成策略 | 生成策略, 创建策略, 推荐策略, 策略建议 |
| evaluate_strategy | 评估策略 | 评估策略, 策略评价, 策略分析, 策略指标 |
| run_backtest | 运行回测 | 回测, 历史测试, 模拟测试, 回测结果 |
| get_market_data | 获取市场数据 | 市场数据, 行情数据, 价格数据, K线数据 |
| get_portfolio_analysis | 获取投资组合分析 | 投资组合, 资产配置, 组合分析, 风险分析 |
| optimize_parameters | 优化策略参数 | 参数优化, 调优, 优化参数, 参数调整 |
| get_alert_history | 获取告警历史 | 告警历史, 预警记录, 异常记录, 告警信息 |

## 使用示例

### 基本使用

```python
from src.modules.intelligence.natural_language_interface import NaturalLanguageInterface
from src.modules.core.llm_integration import EnhancedLLMIntegration

# 初始化大模型集成
llm_integration = EnhancedLLMIntegration()
await llm_integration.initialize({})

# 创建自然语言接口实例
nli = NaturalLanguageInterface(llm_integration)

# 处理自然语言查询
query = "系统现在的运行状态如何？"
result = await nli.process_query(query)
print("处理结果:")
print(result)

# 生成自然语言响应
response = await nli.generate_response(result, query)
print("\n自然语言响应:")
print(response)

# 一步到位的处理和响应
query = "分析一下比特币的市场趋势"
response = await nli.process_and_respond(query)
print("\n查询:", query)
print("响应:", response)
```

### 高级使用 - 带上下文的查询

```python
# 带上下文的查询
context = {
    "user_id": "user123",
    "preferences": {
        "timezone": "Asia/Shanghai",
        "preferred_strategies": ["trend_following", "mean_reversion"]
    },
    "recent_queries": ["比特币的价格是多少？", "以太坊的趋势如何？"]
}

query = "我关注的加密货币有什么投资机会？"
response = await nli.process_and_respond(query, context)
print("带上下文的响应:", response)
```

### 自定义命令

```python
# 添加自定义命令
nli.add_command(
    "get_crypto_news",
    "获取加密货币相关新闻",
    ["加密货币新闻", "数字货币新闻", "币圈新闻", "加密市场新闻"],
    "get_crypto_news"
)

# 查看可用命令
available_commands = nli.get_available_commands()
print("可用命令:", available_commands)

# 使用自定义命令
query = "最近有什么重要的加密货币新闻？"
response = await nli.process_and_respond(query)
print("\n查询:", query)
print("响应:", response)
```

## 与主控制器的集成

自然语言接口已经集成到主控制器中，可以通过主控制器的方法来使用：

```python
from src.modules.main_controller import MainController

# 假设我们有一个主控制器实例
controller = MainController()
await controller.initialize()

# 处理自然语言查询
query = "分析一下以太坊的市场趋势"
result = await controller.process_natural_language_query(query)
print("处理结果:")
print(result)

# 生成自然语言响应
response = await controller.respond_to_natural_language_query(query)
print("\n自然语言响应:")
print(response)

# 获取可用命令
available_commands = controller.get_available_commands()
print("\n可用命令:")
print(available_commands)
```

## 最佳实践

1. **清晰表达**：使用清晰、明确的语言表达查询，避免模糊和歧义
2. **提供上下文**：对于复杂查询，提供足够的上下文信息，帮助系统更好地理解意图
3. **具体问题**：尽量提出具体的问题，避免过于宽泛的查询
4. **反馈修正**：如果系统理解有误，及时提供反馈，帮助系统改进
5. **合理预期**：理解系统的能力边界，不要提出超出系统能力范围的请求

## 常见问题

### Q: 系统无法理解我的查询怎么办？

A: 尝试使用更清晰、更具体的语言重新表达查询，或者提供更多上下文信息。

### Q: 如何提高查询的准确性？

A: 使用系统支持的关键词，保持查询简洁明了，避免使用过于复杂的句子结构。

### Q: 系统可以处理哪些类型的查询？

A: 系统可以处理与交易系统相关的各种查询，包括系统状态、策略性能、市场分析、策略生成、回测等。

### Q: 如何添加新的命令？

A: 可以使用 `add_natural_language_command` 方法添加新的命令，指定命令名称、描述、关键词和关联函数。

### Q: 系统的响应速度如何？

A: 系统的响应速度取决于大模型的处理速度和网络延迟，一般在几秒内可以完成查询处理。