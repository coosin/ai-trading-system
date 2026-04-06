"""
情感智能增强模块 - 参照OpenClaw助理设计

功能：
1. 用户情绪检测
2. 情感自适应回复
3. 主动关心机制
4. 人性化对话增强
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class UserEmotion(Enum):
    """用户情绪类型"""
    NEUTRAL = "neutral"           # 中性
    HAPPY = "happy"               # 开心
    EXCITED = "excited"           # 兴奋
    FRUSTRATED = "frustrated"     # 沮丧/烦躁
    ANXIOUS = "anxious"           # 焦虑
    CONFUSED = "confused"         # 困惑
    ANGRY = "angry"               # 生气
    GRATEFUL = "grateful"         # 感激
    TIRED = "tired"               # 疲惫


class EmotionalIntelligence:
    """
    情感智能增强器
    
    目标：让AI能够理解用户情绪，提供更人性化的回复
    """
    
    def __init__(self, personality_config=None):
        self.personality = personality_config
        
        # 情绪关键词映射
        self.emotion_keywords = {
            UserEmotion.HAPPY: {
                "positive": ["好", "不错", "很好", "棒", "赞", "优秀", "完美", "开心", "高兴"],
                "emoji": ["😊", "😄", "👍", "🎉"]
            },
            UserEmotion.EXCITED: {
                "positive": ["太棒了", "太好了", "暴涨", "大赚", "起飞", "爆发", "激动"],
                "emoji": ["🚀", "💰", "🎯", "🔥"]
            },
            UserEmotion.FRUSTRATED: {
                "negative": ["烦", "累", "不想", "够了", "怎么又", "气", "失望", "郁闷", "糟糕"],
                "emoji": ["😔", "😞", "😤"]
            },
            UserEmotion.ANXIOUS: {
                "negative": ["担心", "害怕", "紧张", "慌", "不安", "会不会", "怎么办", "会不会"],
                "emoji": ["😰", "😥", "🤔"]
            },
            UserEmotion.CONFUSED: {
                "negative": ["不懂", "不明白", "什么是", "什么意思", "怎么", "为什么", "疑惑"],
                "emoji": ["❓", "🤔", "😕"]
            },
            UserEmotion.GRATEFUL: {
                "positive": ["谢谢", "感谢", "多亏", "感恩", "帮忙", "辛苦", "太好了"],
                "emoji": ["🙏", "❤️", "💕"]
            },
            UserEmotion.TIRED: {
                "negative": ["累了", "困", "休息", "不想动", "好烦", "身心俱疲"],
                "emoji": ["😴", "💤", "🛏️"]
            },
            UserEmotion.ANGRY: {
                "negative": ["气", "怒", "垃圾", "坑", "骗", "无语", "太差", "投诉"],
                "emoji": ["😠", "😡", "💢"]
            }
        }
        
        # 情感自适应回复模板
        self.emotion_responses = {
            UserEmotion.HAPPY: {
                "prefix": "很高兴看到你心情不错！",
                "style": "轻松愉快",
                "include_emoji": True
            },
            UserEmotion.EXCITED: {
                "prefix": "太棒了！你的眼光真的很准！",
                "style": "热情激动",
                "include_emoji": True
            },
            UserEmotion.FRUSTRATED: {
                "prefix": "我理解你的感受，投资市场确实让人头疼。",
                "style": "温柔共情",
                "include_emoji": True,
                "action": "先安抚，再分析"
            },
            UserEmotion.ANXIOUS: {
                "prefix": "别太担心，我们一起来分析一下情况。",
                "style": "稳定人心",
                "include_emoji": True,
                "action": "提供确定性信息"
            },
            UserEmotion.CONFUSED: {
                "prefix": "完全理解你的困惑，让我详细解释一下。",
                "style": "耐心细致",
                "include_emoji": False,
                "action": "分步骤解释"
            },
            UserEmotion.GRATEFUL: {
                "prefix": "不客气！能帮到你我也很开心。",
                "style": "温暖真诚",
                "include_emoji": True
            },
            UserEmotion.TIRED: {
                "prefix": "辛苦了，先休息一下吧，市场永远都在。",
                "style": "关心体贴",
                "include_emoji": True,
                "action": "提醒休息"
            },
            UserEmotion.ANGRY: {
                "prefix": "我理解你的不满，让我帮你看看是什么问题。",
                "style": "严肃认真",
                "include_emoji": False,
                "action": "解决问题为主"
            }
        }
        
        # 关心场景检测
        self.care_scenarios = {
            "long_inactive": {
                "threshold_hours": 24,
                "keywords": ["好久", "没见", "一直没", "很久"],
                "message": "最近市场波动较大，你的心情还好吗？有什么需要我帮忙分析的吗？"
            },
            "continuous_loss": {
                "threshold_trades": 3,
                "keywords": ["连续", "亏损", "跌", "亏"],
                "message": "市场波动确实比较大，我们一起冷静分析一下，看看有没有优化空间。"
            },
            "big_profit": {
                "threshold_percent": 10,
                "keywords": ["大赚", "暴涨", "翻倍", "赚翻"],
                "message": "太棒了！这次策略执行得非常漂亮！记得注意风险，继续保持！"
            },
            "system_error": {
                "keywords": ["错误", "失败", "异常", "bug"],
                "message": "系统遇到了小问题，我正在处理中。不用担心，我会及时通知你进展。"
            },
            "user_stressed": {
                "keywords": ["压力", "焦虑", "担心", "怕"],
                "message": "投资是一场马拉松，保持好心态最重要。我们一起慢慢来。"
            }
        }
        
        logger.info("✅ 情感智能增强器初始化完成")
    
    def detect_emotion(self, user_message: str) -> Tuple[UserEmotion, float]:
        """
        检测用户情绪
        
        Returns:
            (情绪类型, 置信度)
        """
        message = user_message.lower().strip()
        
        emotion_scores = {emotion: 0.0 for emotion in UserEmotion}
        
        for emotion, keywords_data in self.emotion_keywords.items():
            score = 0
            
            # 检查正面关键词
            if "positive" in keywords_data:
                for kw in keywords_data["positive"]:
                    if kw in message:
                        score += 1
            
            # 检查负面关键词
            if "negative" in keywords_data:
                for kw in keywords_data["negative"]:
                    if kw in message:
                        score += 1
            
            if score > 0:
                emotion_scores[emotion] = score
        
        # 找出最高分数的情绪
        if not emotion_scores or max(emotion_scores.values()) == 0:
            return UserEmotion.NEUTRAL, 0.5
        
        max_emotion = max(emotion_scores, key=emotion_scores.get)
        max_score = emotion_scores[max_emotion]
        
        # 置信度归一化
        confidence = min(1.0, max_score / 3.0)
        
        return max_emotion, confidence
    
    def adapt_response(self, response: str, user_emotion: UserEmotion) -> str:
        """
        根据用户情绪自适应回复
        
        Args:
            response: 原始回复
            user_emotion: 检测到的用户情绪
            
        Returns:
            优化后的回复
        """
        if user_emotion == UserEmotion.NEUTRAL:
            return response
        
        emotion_config = self.emotion_responses.get(user_emotion, {})
        
        # 添加前缀
        prefix = emotion_config.get("prefix", "")
        
        # 添加合适的emoji
        if emotion_config.get("include_emoji", False):
            emoji = self._get_emoji_for_emotion(user_emotion)
            response = f"{prefix} {response} {emoji}"
        else:
            response = f"{prefix} {response}"
        
        return response
    
    def _get_emoji_for_emotion(self, emotion: UserEmotion) -> str:
        """获取情绪对应的emoji"""
        emoji_map = {
            UserEmotion.HAPPY: "😊",
            UserEmotion.EXCITED: "🚀",
            UserEmotion.FRUSTRATED: "💪",  # 鼓励
            UserEmotion.ANXIOUS: "🤗",  # 拥抱
            UserEmotion.CONFUSED: "💡",  # 启发
            UserEmotion.GRATEFUL: "❤️",
            UserEmotion.TIRED: "💤",
            UserEmotion.ANGRY: "🛠️"  # 解决问题
        }
        return emoji_map.get(emotion, "")
    
    def should_show_care(self, user_message: str, last_active_hours: float = None,
                         recent_trades: int = None, recent_pnl: float = None) -> Optional[str]:
        """
        判断是否需要主动关心用户
        
        Returns:
            关心消息，如果不需要则返回None
        """
        message = user_message.lower()
        
        # 检查关键词触发
        for scenario, config in self.care_scenarios.items():
            for kw in config["keywords"]:
                if kw in message:
                    return None  # 用户主动发言，不需要主动关心
        
        # 检查长时间未活跃
        if last_active_hours and last_active_hours > 24:
            if last_active_hours > config.get("threshold_hours", 24):
                return self.care_scenarios["long_inactive"]["message"]
        
        # 检查连续亏损
        if recent_trades and recent_trades >= 3 and recent_pnl and recent_pnl < 0:
            return self.care_scenarios["continuous_loss"]["message"]
        
        # 检查大盈利
        if recent_pnl and recent_pnl > 10:
            return self.care_scenarios["big_profit"]["message"]
        
        return None
    
    def get_encouragement(self, context: str = "general") -> str:
        """获取鼓励性消息"""
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
    
    def generate_natural_response(self, user_message: str, base_response: str,
                                  user_emotion: UserEmotion = None) -> str:
        """
        生成更自然的回复
        
        核心功能：让回复更像人类对话
        """
        # 如果没有检测到情绪，先检测
        if user_emotion is None:
            user_emotion, _ = self.detect_emotion(user_message)
        
        # 根据情绪调整回复
        adapted_response = self.adapt_response(base_response, user_emotion)
        
        # 添加一些人性化的点缀
        if user_emotion in [UserEmotion.HAPPY, UserEmotion.EXCITED]:
            # 开心时更活泼
            if not any(x in adapted_response for x in ["！", "😊", "🚀"]):
                adapted_response = adapted_response.rstrip("。") + "！"
        
        elif user_emotion in [UserEmotion.FRUSTRATED, UserEmotion.ANXIOUS]:
            # 沮丧时更温柔
            if "我理解" not in adapted_response and "别担心" not in adapted_response:
                adapted_response = "我理解你的感受。" + adapted_response
        
        return adapted_response


# 便捷函数
def create_emotional_intelligence() -> EmotionalIntelligence:
    """创建情感智能实例"""
    return EmotionalIntelligence()


# 导出
__all__ = [
    'UserEmotion',
    'EmotionalIntelligence', 
    'create_emotional_intelligence'
]