"""
主控制器集成脚本 - 将新功能集成到主控制器

这个脚本展示了如何在主控制器中集成：
1. 统一记忆网关 MemoryGateway（替代已移除的 HierarchicalMemoryManager）
2. 技能管理器
3. 心跳监控器
4. 智能通知系统
"""

# 在主控制器的导入部分添加：
"""
from src.modules.memory.memory_gateway import MemoryGateway
from src.modules.skills import (
    SkillManager, 
    SystemDiagnosisSkill,
    PerformanceAnalysisSkill,
    RiskAssessmentSkill,
    OptimizationSkill,
    AutoRepairSkill
)
from src.modules.core.heartbeat_monitor import HeartbeatMonitor
from src.modules.core.smart_notification import SmartNotificationSystem
"""

# 在MainController的__init__方法中添加：
"""
def __init__(self, config_manager=None):
    # ... 现有代码 ...
    
    # 新增：智能系统组件（记忆请走 MemoryGateway / main_controller.memory_gateway）
    self.memory_manager = None  # 或 MemoryGateway(...)
    self.skill_manager = SkillManager()
    self.smart_notification = SmartNotificationSystem(
        send_func=self._send_notification
    )
    self.heartbeat_monitor = None  # 在启动时初始化
    
    # 注册技能
    self._register_skills()
    
    logger.info("智能系统组件初始化完成")

def _register_skills(self):
    \"\"\"注册所有技能\"\"\"
    self.skill_manager.register_skill(SystemDiagnosisSkill())
    self.skill_manager.register_skill(PerformanceAnalysisSkill())
    self.skill_manager.register_skill(RiskAssessmentSkill())
    self.skill_manager.register_skill(OptimizationSkill())
    self.skill_manager.register_skill(AutoRepairSkill())
    
    logger.info(f"已注册 {len(self.skill_manager.skills)} 个技能")
"""

# 在启动方法中添加：
"""
async def start(self):
    \"\"\"启动主控制器\"\"\"
    # ... 现有启动代码 ...
    
    # 启动智能系统组件
    await self._start_intelligent_systems()
    
    logger.info("✅ 主控制器启动完成")

async def _start_intelligent_systems(self):
    \"\"\"启动智能系统组件\"\"\"
    logger.info("🚀 启动智能系统组件...")
    
    # 初始化心跳监控器
    trading_engine = self.modules.get("trading_engine")
    if trading_engine:
        self.heartbeat_monitor = HeartbeatMonitor(
            trading_engine=trading_engine.module,
            skill_manager=self.skill_manager,
            memory_manager=self.memory_manager,
            notification_handler=self.smart_notification.send,
            interval=1800  # 30分钟
        )
        
        # 启动心跳监控
        heartbeat_task = asyncio.create_task(self.heartbeat_monitor.start())
        self._tasks.append(heartbeat_task)
    
    logger.info("✅ 智能系统组件启动完成")
"""

# 在停止方法中添加：
"""
async def stop(self):
    \"\"\"停止主控制器\"\"\"
    logger.info("🛑 停止主控制器...")
    
    # 停止心跳监控
    if self.heartbeat_monitor:
        self.heartbeat_monitor.stop()
    
    # 清空通知队列
    await self.smart_notification.flush()
    
    # 保存记忆
    await self._save_final_memories()
    
    # ... 现有停止代码 ...
    
    logger.info("✅ 主控制器已停止")

async def _save_final_memories(self):
    \"\"\"保存最终记忆\"\"\"
    try:
        summary = f\"\"\"
# 系统关闭总结 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 运行统计
- 运行时间: {datetime.now() - self.start_time if self.start_time else 'N/A'}
- 处理事件: {self.metrics['total_events']}
- 错误次数: {self.metrics['total_errors']}
- 模块启动: {self.metrics['module_starts']}
- 模块停止: {self.metrics['module_stops']}

## 技能执行统计
{json.dumps(self.skill_manager.get_execution_stats(), indent=2)}

## 系统状态
- 最终状态: {self.system_status.value}
- 活跃模块: {sum(1 for m in self.modules.values() if m.status == ModuleStatus.RUNNING)}
\"\"\"
        
        await self.memory_manager.save_daily_memory(summary)
        logger.info("✅ 最终记忆已保存")
    except Exception as e:
        logger.error(f"保存最终记忆失败: {e}")
"""

# 添加通知处理方法：
"""
async def _send_notification(self, title: str, message: str, priority: str = "medium"):
    \"\"\"发送通知\"\"\"
    try:
        # 发送到Telegram
        if hasattr(self, 'telegram_bot') and self.telegram_bot:
            await self.telegram_bot.send_message(
                f"{title}\\n\\n{message}"
            )
        
        # 记录到日志
        logger.info(f"📢 [{priority.upper()}] {title}")
        
    except Exception as e:
        logger.error(f"发送通知失败: {e}")
"""

# 添加健康检查增强：
"""
async def _enhanced_health_check(self) -> Dict[str, Any]:
    \"\"\"增强的健康检查\"\"\"
    # 执行原有健康检查
    basic_health = await self._basic_health_check()
    
    # 执行技能健康检查
    context = {
        "trading_engine": self.modules.get("trading_engine"),
        "performance_data": basic_health.get("metrics", {})
    }
    
    skill_health = await self.skill_manager.run_health_check(context)
    
    # 合并结果
    return {
        **basic_health,
        "intelligent_systems": {
            "memory": await self.memory_manager.get_memory_summary(),
            "skills": self.skill_manager.get_execution_stats(),
            "heartbeat": self.heartbeat_monitor.get_status() if self.heartbeat_monitor else None,
            "notifications": self.smart_notification.get_stats()
        },
        "skill_health": skill_health
    }
"""

print("""
集成说明：
1. 将上述代码片段添加到 main_controller.py 的相应位置
2. 确保所有导入都正确
3. 测试启动和停止流程
4. 验证所有新功能正常工作

关键集成点：
- __init__: 初始化智能系统组件
- start(): 启动心跳监控
- stop(): 保存记忆和清理资源
- _send_notification(): 统一通知接口
- _enhanced_health_check(): 增强健康检查
""")
