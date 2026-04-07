# 开平仓与动态止盈止损联动说明

## 目标

把“开仓前自适应门控”与“开仓后仓位跟踪止盈止损”打通，形成统一的风险-执行闭环：

1. 开仓前：依据实时行情（价差、深度、波动）判断是否允许开仓；
2. 开仓时：把门控结果映射成该仓位的初始止盈止损参数；
3. 持仓中：根据实时订单簿持续微调止盈止损；
4. 触发后：通过 `ExecutionGateway` 执行真实平仓，保持 S1 单一执行出口约束。

---

## 流程链路

### 1) 开仓时机控制（AICoreDecisionEngine）

入口：`AICoreDecisionEngine._execute_decision()`

- 使用分组/时段阈值（如 `BTC@US`）读取有效门控：
  - `min_rr_to_trade`
  - `max_spread_bps_to_trade`
  - `max_abs_depth_imbalance_to_trade`
- 再叠加波动率自适应（低波收紧、高波放宽）得到 `effective_*`。
- 若 RR、价差、深度任一不满足，拒绝开仓。

### 2) 开仓后立刻同步 SL/TP 跟踪（AICoreDecisionEngine -> MainController -> SLTP Manager）

开仓成功后调用：`AICoreDecisionEngine._sync_dynamic_sltp_after_open()`

- 将开仓决策中的 `entry/stop/tp` 转换为百分比参数；
- 若当前 RR 小于门槛，按 `min_rr` 抬高止盈距离；
- 按有效价差阈值推导 `trailing_offset`（价差越大，越保守）；
- 将 `guard_profile`、开仓时盘口状态写入 metadata；
- 通过 `MainController.create_stop_loss_order(...)` 创建跟踪单。

### 3) 持仓中动态调整（StopLossTakeProfitManager）

入口：`StopLossTakeProfitManager.update_price()`  
新增：`_dynamic_market_adjust()`

- 每次价格更新前，先做动态调整（带最小间隔）；
- 读取实时订单簿：
  - `spread_bps`
  - `depth_imbalance`
- 在“浮盈阶段”执行策略：
  - 若盘口不利（高价差/逆向失衡）=> 收紧止损，优先保利润；
  - 若盘口有利（顺向失衡）=> 轻微延展止盈，争取趋势延续。
- 所有调整写入 metadata 和统计项 `dynamic_adjustments`。

### 4) 触发平仓（S1 合规）

当 SL/TP/时间止损触发时：

- `StopLossTakeProfitManager` 优先经 `ExecutionGateway.close_swap(...)` 发起平仓；
- 若网关不可用才回退交易所方法；
- 保证风控平仓也尽量在统一执行出口下完成。

---

## 关键配置

### AI 开仓门控

- `min_rr_to_trade`
- `max_spread_bps_to_trade`
- `max_abs_depth_imbalance_to_trade`
- `auto_adaptive_guards`
- `auto_tune_*`（全局/分组/时段学习）

### 动态 SL/TP 跟踪

- `enable_dynamic_market_adjustment`（默认开启）
- `dynamic_update_min_interval_sec`（默认 20 秒）
- `dynamic_tighten_ratio`（默认 0.15）
- `dynamic_tp_extend_ratio`（默认 0.10）

---

## 策略开发建议（落地规范）

1. 所有新策略在产出开仓信号时，必须提供可解释的 `entry/stop/tp`；
2. 开仓前仅通过 `_execute_decision()` 的门控链路，不绕过；
3. 开仓成功后必须创建对应 `index_key=symbol|side` 的跟踪单；
4. 持仓跟踪参数修改必须通过 `StopLossTakeProfitManager`，保持审计一致；
5. 触发平仓统一走 `ExecutionGateway`，避免多出口并发写单。

---

## 观测与排障

- 关注日志关键词：
  - `执行门控拒绝`
  - `同步止盈止损跟踪`
  - `动态调整SL/TP`
  - `止盈止损实盘平仓已提交`
- 关注状态：
  - `execution_guards`（config/adaptive_profile/stats）
  - `stop_loss_manager` 统计（含 `dynamic_adjustments`）
