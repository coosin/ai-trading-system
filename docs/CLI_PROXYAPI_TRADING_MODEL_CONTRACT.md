# CLIProxyAPI Trading Model Contract

## Goal

让交易系统只对接一个统一的 OpenAI 兼容入口，但不把“选什么真实模型”完全交给网关自由发挥。

这份契约的核心原则是：

- 交易系统只选择逻辑能力槽位，不直接依赖真实模型名
- `CLIProxyAPI` 负责把逻辑能力槽位映射到当前可用的真实模型
- 新模型只有通过对应槽位验收，才能进入生产路由
- 交易系统继续保留输出校验、降级和熔断，不盲信上游结果

## Responsibility Split

### Trading System

- 只按任务语义选择逻辑模型别名
- 继续保留 task 级熔断、输出校验、回退和降级
- 监控每个逻辑别名的成功率、延迟、解析率和业务质量

### CLIProxyAPI

- 统一承载真实模型、账号、供应商和路由
- 管理同一逻辑别名背后的真实模型候选
- 在同一逻辑别名内部做凭据级切换、容灾和限流
- 不直接替交易系统跨能力槽位做“智能改派”

## Logical Aliases

建议至少保留以下 4 个生产槽位。

### `trading-fast`

用途：
- `general`
- `market_analysis`
- `news_analysis`
- `risk_assessment`
- `signal_generation`

要求：
- 优先低延迟
- 允许推理深度一般
- 必须能够稳定返回简洁内容
- 结构化任务必须具备较高 JSON 可解析率

准入门槛：
- 小样本成功率 `>= 98%`
- P95 延迟 `<= 8s`
- 结构化输出可解析率 `>= 95%`
- 不得频繁出现 markdown 代码块包裹 JSON

### `trading-reasoning`

用途：
- `decision_making`
- `reasoning`
- 复杂策略审查

要求：
- 优先稳定性和推理质量
- 允许延迟高于 `trading-fast`
- 必须输出可约束、可审计的决策字段

准入门槛：
- 小样本成功率 `>= 97%`
- P95 延迟 `<= 15s`
- 决策字段完整率 `>= 95%`
- 不得频繁出现动作和风控字段互相矛盾

### `trading-json`

用途：
- 任何“严格结构化返回”优先任务
- 可作为 `market_analysis` / `strategy_generation` / `risk_assessment` 的强化槽位

要求：
- 以结构化稳定性优先
- 响应可以比 `trading-fast` 略慢
- 对 fenced code block、解释性前后缀容忍度要低

准入门槛：
- JSON 可解析率 `>= 99%`
- 字段齐全率 `>= 98%`
- 不得把 JSON 长期包在 markdown 代码块里

### `trading-fallback`

用途：
- 上述任一槽位不可用时的保底降级

要求：
- 首先保证“可回”
- 输出质量可以一般，但必须尽量稳定
- 不能经常返回空字符串或超长失控文本

准入门槛：
- 成功率 `>= 99%`
- 必须在失败场景下可预测
- 允许保守输出，但不能破坏下游解析和风控

## Routing Rules

### Strong Recommendation

- 交易系统按任务绑定逻辑别名
- `CLIProxyAPI` 只在同一逻辑别名内部切换真实模型
- 不要让 `CLIProxyAPI` 在 `trading-fast` 和 `trading-reasoning` 之间自行跳转

### Production Mapping Suggestion

- `general -> trading-fast`
- `market_analysis -> trading-json`
- `strategy_generation -> trading-json`
- `signal_generation -> trading-fast`
- `risk_assessment -> trading-json`
- `news_analysis -> trading-fast`
- `decision_making -> trading-reasoning`
- `reasoning -> trading-reasoning`

## Onboarding Checklist For New Real Models

任何新模型或新供应商进入 `CLIProxyAPI` 前，建议按以下顺序验收：

1. 连通性
- `/v1/chat/completions` 基础请求稳定返回
- 连续 10 次无明显 `500/EOF`

2. 限流与稳定性
- 连续结构化请求下无明显 `429` 风暴
- 不因内部重试放大故障

3. JSON 纪律
- 严格 JSON 提示词下可稳定返回对象
- markdown 代码块、解释性前缀比例可接受

4. 决策质量
- 动作、方向、仓位、杠杆、信心、止损止盈字段一致
- 不明显违背交易规则

5. 降级行为
- 失败时错误模式可预测
- 不返回异常长文本或完全空内容

回归验收可直接运行：

```bash
python3 scripts/validate_trading_model_aliases.py
# 或统一入口
python3 scripts/verify.py trading-models
```

当前期望 owner / upstream model 固化在：

- `config/trading_model_alias_expectations.json`

如果 `CLIProxyAPI` 背后的真实供应商或真实模型有意变更，先改该文件，再执行上述回归验收。

## Operational Guardrails

### CLIProxyAPI Side

- 同一逻辑别名内部再做真实模型切换
- 优先开启粘性路由，降低短时抖动带来的画像污染
- 控制网关重试次数，避免和交易系统形成嵌套重试风暴

### Trading System Side

- 保留 `safe_json_parse()`
- 保留 task 级 circuit breaker
- 保留解析失败后的 `hold` / 保守降级
- 监控逻辑别名，而不是只监控真实模型名

## Example Alias Policy

下面是推荐的人类约定，不要求当前代码立刻支持：

```yaml
llm:
  default_model: trading-fast
  models:
    - model_id: trading-fast
      provider: openai
      base_url: http://127.0.0.1:8317/v1
      notes: "CLIProxyAPI logical alias for low-latency trading tasks"
    - model_id: trading-json
      provider: openai
      base_url: http://127.0.0.1:8317/v1
      notes: "CLIProxyAPI logical alias for strict structured-output tasks"
    - model_id: trading-reasoning
      provider: openai
      base_url: http://127.0.0.1:8317/v1
      notes: "CLIProxyAPI logical alias for deep reasoning tasks"
    - model_id: trading-fallback
      provider: openai
      base_url: http://127.0.0.1:8317/v1
      notes: "CLIProxyAPI logical alias for fallback routing"
  task_model_mapping:
    general: [trading-fast, trading-fallback]
    market_analysis: [trading-json, trading-fast, trading-fallback]
    strategy_generation: [trading-json, trading-fast, trading-fallback]
    signal_generation: [trading-fast, trading-fallback]
    risk_assessment: [trading-json, trading-fast, trading-fallback]
    news_analysis: [trading-fast, trading-fallback]
    decision_making: [trading-reasoning, trading-fallback]
    reasoning: [trading-reasoning, trading-fallback]
```

## Decision Rule

如果一个真实模型“能用但不稳定”，不要直接放进主槽位。

优先级建议：

- 先进入 `trading-fallback`
- 再进入 `trading-fast` 或 `trading-json`
- 最后才进入 `trading-reasoning`

这样即使上游经常增减模型、切换供应商，交易系统仍然只面对稳定的逻辑契约，而不是频繁变化的真实模型名。
