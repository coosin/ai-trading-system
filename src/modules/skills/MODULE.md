# Skills System - 技能系统说明

## 概述

技能系统赋予交易系统自我认知、自我维护和自我优化能力。

## 核心技能

### 1. 系统自检 (System Diagnosis)
- **优先级**: CRITICAL
- **功能**: 诊断系统健康状态
- **检查项**: CPU、内存、磁盘、网络、进程
- **执行频率**: 每次心跳

### 2. 性能分析 (Performance Analysis)
- **优先级**: HIGH
- **功能**: 分析交易表现
- **指标**: 胜率、盈亏比、最大回撤
- **执行频率**: 每次心跳

### 3. 风险评估 (Risk Assessment)
- **优先级**: CRITICAL
- **功能**: 评估当前风险
- **评估项**: 账户风险、持仓风险、市场风险
- **执行频率**: 每次心跳

### 4. 优化建议 (Optimization)
- **优先级**: MEDIUM
- **功能**: 提供优化建议
- **建议类型**: 策略优化、风险控制、性能优化
- **执行频率**: 按需

### 5. 自动修复 (Auto Repair)
- **优先级**: HIGH
- **功能**: 自动修复常见问题
- **修复项**: 日志轮转、缓存清理、过期持仓
- **执行频率**: 每3小时

## 使用示例

```python
from src.modules.skills import SkillManager, SystemDiagnosisSkill

# 创建技能管理器
manager = SkillManager()

# 注册技能
manager.register_skill(SystemDiagnosisSkill())

# 执行技能
context = {"trading_engine": engine}
result = await manager.execute_skill("system_diagnosis", context)

# 执行所有技能
results = await manager.execute_all_skills(context)

# 运行健康检查
health_report = await manager.run_health_check(context)
```

## 技能开发

创建自定义技能需要继承 `SkillBase` 类：

```python
from src.modules.skills.skill_base import SkillBase, SkillResult, SkillPriority

class CustomSkill(SkillBase):
    def __init__(self):
        super().__init__(
            name="custom_skill",
            description="自定义技能",
            priority=SkillPriority.MEDIUM
        )
    
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        # 实现技能逻辑
        return SkillResult(
            skill_name=self.name,
            status=SkillStatus.SUCCESS,
            priority=self.priority,
            message="执行成功"
        )
    
    async def diagnose(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # 实现诊断逻辑
        return {"status": "ok"}
```

## 配置选项

```python
skill_config = {
    "enabled": True,        # 是否启用
    "auto_fix": False,      # 是否自动修复
    "interval": 3600        # 执行间隔（秒）
}
```

## 最佳实践

1. **优先级设置**: 关键技能设置为CRITICAL，确保优先执行
2. **错误处理**: 技能执行失败不应影响系统运行
3. **资源管理**: 避免技能占用过多资源
4. **日志记录**: 记录技能执行过程和结果

## 更新日志

- 2026-04-04: 初始版本发布
- 2026-04-04: 添加5个核心技能
