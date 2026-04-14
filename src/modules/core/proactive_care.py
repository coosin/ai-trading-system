"""
主动关怀系统 - 让AI不再被动

功能：
1. 主动关心用户状态
2. 定期检查交易状态
3. 发现异常主动提醒
4. 情感支持与鼓励
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CareScenario:
    """关怀场景"""
    name: str
    check_condition: str  # 检查条件
    keywords: List[str]   # 触发关键词
    message: str          # 关怀消息
    priority: str = "normal"


class ProactiveCareSystem:
    """
    主动关怀系统
    
    目标：让AI从被动回答变为主动关心
    """
    
    def __init__(self, main_controller=None):
        self.main_controller = main_controller
        
        # 关怀场景配置
        self.care_scenarios = [
            CareScenario(
                name="long_inactive",
                check_condition="last_message_hours > 24",
                keywords=["好久", "没见", "一直没", "很久"],
                message="嗨！最近怎么样？好久没见你操作了，市场有些波动，要不要一起看看？"
            ),
            CareScenario(
                name="continuous_loss",
                check_condition="consecutive_losses >= 3",
                keywords=["连续", "亏损", "跌", "亏"],
                message="我注意到最近市场波动较大，你的持仓有些挑战。别担心，我们一起分析一下，看看需要怎么调整。"
            ),
            CareScenario(
                name="big_profit",
                check_condition="profit_percent > 10",
                keywords=["大赚", "暴涨", "翻倍", "赚翻"],
                message="太棒了！这次的策略执行得非常漂亮！为你感到高兴！🎉 记得注意风险，继续保持！"
            ),
            CareScenario(
                name="system_error",
                check_condition="has_error",
                keywords=["错误", "失败", "异常", "bug"],
                message="系统遇到了点小问题，我正在处理中。不用担心，我会及时通知你进展。"
            ),
            CareScenario(
                name="user_stressed",
                check_condition="user_mood == 'stressed'",
                keywords=["压力", "焦虑", "担心", "怕"],
                message="投资是一场马拉松，保持好心态最重要。我理解你的担心，让我们一起慢慢分析。"
            ),
            CareScenario(
                name="morning_greeting",
                check_condition="time == 'morning'",
                keywords=["早上", "早安", "morning"],
                message="早上好！新的一天新的机会！让我帮你看看今天的市场情况。"
            ),
            CareScenario(
                name="evening_care",
                check_condition="time == 'evening'",
                keywords=["晚上", "晚安", "evening"],
                message="晚上好！今天的交易怎么样？记得不要熬夜，注意休息。"
            )
        ]
        
        # 状态追踪
        self.last_care_time = datetime.now()
        self.last_user_message_time = datetime.now()
        self.consecutive_losses = 0
        self.last_pnl = 0.0
        self.care_cooldown_minutes = 30  # 关怀冷却时间
        
        # 主动行为配置
        self.enable_proactive_messages = True
        self.proactive_check_interval_seconds = 300  # 5分钟检查一次
        
        logger.info("✅ 主动关怀系统初始化完成")
    
    async def initialize(self) -> bool:
        """异步初始化"""
        # 启动主动检查任务
        asyncio.create_task(self._proactive_check_loop())
        return True
    
    async def _proactive_check_loop(self):
        """主动检查循环"""
        while True:
            try:
                await asyncio.sleep(self.proactive_check_interval_seconds)
                
                if self.enable_proactive_messages:
                    care_message = await self.check_and_generate_care()
                    if care_message:
                        logger.info(f"💬 主动关怀: {care_message}")
                        # 这里可以发送消息给用户
                        
            except Exception as e:
                logger.error(f"主动检查循环错误: {e}")
    
    async def check_and_generate_care(self) -> Optional[str]:
        """检查是否需要主动关心用户"""
        
        # 检查冷却时间
        time_since_last_care = (datetime.now() - self.last_care_time).total_seconds()
        if time_since_last_care < self.care_cooldown_minutes * 60:
            return None
        
        # 检查用户活跃时间
        time_since_last_message = (datetime.now() - self.last_user_message_time).total_seconds()
        
        # 长时间不活跃
        if time_since_last_message > 24 * 3600:  # 24小时
            self.last_care_time = datetime.now()
            return self.care_scenarios[0].message  # long_inactive
        
        # 检查连续亏损
        if self.consecutive_losses >= 3:
            self.last_care_time = datetime.now()
            return self.care_scenarios[1].message  # continuous_loss
        
        # 检查大盈利
        if self.last_pnl > 10:
            self.last_care_time = datetime.now()
            return self.care_scenarios[2].message  # big_profit
        
        return None
    
    def record_user_message(self, message: str):
        """记录用户消息，更新活跃时间"""
        self.last_user_message_time = datetime.now()
        
        # 检查消息中的关键词
        for scenario in self.care_scenarios:
            for kw in scenario.keywords:
                if kw in message:
                    logger.info(f"检测到关怀关键词: {kw} ({scenario.name})")
                    break
    
    def record_trade_result(self, pnl: float, is_profit: bool):
        """记录交易结果"""
        if is_profit:
            self.consecutive_losses = 0
            self.last_pnl = pnl
        else:
            self.consecutive_losses += 1
            self.last_pnl = pnl
    
    def record_error(self, error: str):
        """记录系统错误"""
        logger.info(f"记录系统错误: {error}")
        # 可以在这里触发系统错误关怀
    
    async def generate_care_response(self, user_message: str) -> Optional[str]:
        """
        根据用户消息生成关怀回复
        在用户消息后添加适当的关怀语
        """
        message_lower = user_message.lower()
        
        # 检查是否需要添加关怀
        for scenario in self.care_scenarios:
            for kw in scenario.keywords:
                if kw in message_lower:
                    # 根据场景添加不同的关怀回复
                    if scenario.name == "morning_greeting":
                        return "早上好！今天状态怎么样？有什么需要我帮忙的吗？"
                    elif scenario.name == "evening_care":
                        return "晚上好！今天辛苦了。交易还顺利吗？"
        
        return None
    
    def get_encouragement(self, context: str = "general") -> str:
        """获取鼓励消息"""
        encouragements = {
            "general": [
                "你的策略思路很清晰，继续坚持！",
                "每次复盘都是进步的机会，做得很好！",
                "市场虽有波动，但你的风险管理很稳健。",
                "相信你的判断，我会全力支持你！"
            ],
            "loss": [
                "亏损是成长的一部分，保持冷静分析。",
                "市场波动是正常的，重要的是策略应对。",
                "我们一起找出问题，优化策略。"
            ],
            "success": [
                "太棒了！继续保持这个势头！",
                "你的努力得到了回报！",
                "这次决策非常明智！"
            ]
        }
        
        import random
        return random.choice(encouragements.get(context, encouragements["general"]))
    
    def should_respond_proactively(self) -> bool:
        """判断是否应该主动发言"""
        if not self.enable_proactive_messages:
            return False
        
        # 检查冷却
        time_since_last_care = (datetime.now() - self.last_care_time).total_seconds()
        return time_since_last_care >= self.care_cooldown_minutes * 60


# 便捷函数
def create_proactive_care_system(main_controller=None) -> ProactiveCareSystem:
    """创建主动关怀系统实例"""
    return ProactiveCareSystem(main_controller)


__all__ = [
    'ProactiveCareSystem',
    'CareScenario',
    'create_proactive_care_system'
]