"""
用户指令智能识别器
自动识别用户输入中的指令、偏好和重要信息
"""
import re
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class UserIntentType(Enum):
    """用户意图类型"""
    PREFERENCE = "preference"
    INSTRUCTION = "instruction"
    RISK_SETTING = "risk_setting"
    TRADING_RULE = "trading_rule"
    REMINDER = "reminder"
    PROHIBITION = "prohibition"
    GOAL = "goal"
    FEEDBACK = "feedback"


@dataclass
class ExtractedIntent:
    """提取的用户意图"""
    intent_type: UserIntentType
    content: str
    original_text: str
    confidence: float
    keywords: List[str]
    metadata: Dict[str, Any]


class UserIntentRecognizer:
    """
    用户意图识别器
    
    自动识别用户输入中的：
    1. 用户偏好（喜欢、偏好、习惯）
    2. 系统指令（记住、以后、总是）
    3. 风险设置（止损、仓位、杠杆）
    4. 交易规则（不要、必须、避免）
    5. 提醒事项（记得、别忘了）
    6. 禁止事项（不要、禁止、不能）
    7. 目标设定（目标、期望）
    8. 反馈意见（太、很、不够）
    """
    
    PATTERNS = {
        UserIntentType.PREFERENCE: [
            (r"我(比较|更|最)?喜欢(.+)", "喜欢"),
            (r"我(比较|更|最)?偏好(.+)", "偏好"),
            (r"我(通常|一般|习惯)(.+)", "习惯"),
            (r"我的(.+)(偏好|喜好|习惯)(是|为)[：:]?\s*(.+)", "偏好设置"),
            (r"我倾向于(.+)", "倾向"),
            (r"我更倾向于(.+)", "倾向"),
            (r"我偏好(.+)", "偏好"),
            (r"我主要交易(.+)", "交易偏好"),
            (r"我擅长(.+)", "擅长"),
        ],
        
        UserIntentType.INSTRUCTION: [
            (r"记住[：:]?\s*(.+)", "记住"),
            (r"记得[：:]?\s*(.+)", "记得"),
            (r"请记住(.+)", "记住"),
            (r"要记住(.+)", "记住"),
            (r"以后(.+)", "以后"),
            (r"从今以后(.+)", "以后"),
            (r"以后都(.+)", "以后"),
            (r"以后请(.+)", "以后"),
            (r"总是(.+)", "总是"),
            (r"每次(.+)", "每次"),
            (r"一直(.+)", "一直"),
            (r"保持(.+)", "保持"),
            (r"持续(.+)", "持续"),
        ],
        
        UserIntentType.RISK_SETTING: [
            (r"止损[是为：:]\s*(.+)", "止损"),
            (r"止盈[是为：:]\s*(.+)", "止盈"),
            (r"仓位[是为：:]\s*(.+)", "仓位"),
            (r"杠杆[是为：:]\s*(.+)", "杠杆"),
            (r"最大亏损[是为：:]\s*(.+)", "最大亏损"),
            (r"风险偏好[是为：:]\s*(.+)", "风险偏好"),
            (r"风险承受[是为：:]\s*(.+)", "风险承受"),
            (r"我是(.+型).*(?:投资者|交易者)", "投资者类型"),
            (r"风险等级[是为：:]\s*(.+)", "风险等级"),
            (r"单笔最大[是为：:]\s*(.+)", "单笔限制"),
            (r"日最大亏损[是为：:]\s*(.+)", "日亏损限制"),
        ],
        
        UserIntentType.TRADING_RULE: [
            (r"不要(.+)", "禁止"),
            (r"禁止(.+)", "禁止"),
            (r"不能(.+)", "禁止"),
            (r"避免(.+)", "避免"),
            (r"必须(.+)", "必须"),
            (r"一定要(.+)", "必须"),
            (r"务必(.+)", "必须"),
            (r"只在(.+)时(.+)", "条件交易"),
            (r"当(.+)时才(.+)", "条件交易"),
            (r"如果(.+)就(.+)", "条件规则"),
        ],
        
        UserIntentType.REMINDER: [
            (r"别忘了(.+)", "提醒"),
            (r"不要忘记(.+)", "提醒"),
            (r"注意(.+)", "注意"),
            (r"留意(.+)", "留意"),
            (r"关注(.+)", "关注"),
            (r"提醒我(.+)", "提醒"),
            (r"到时候提醒我(.+)", "提醒"),
        ],
        
        UserIntentType.PROHIBITION: [
            (r"绝对不要(.+)", "绝对禁止"),
            (r"千万不要(.+)", "绝对禁止"),
            (r"一定不要(.+)", "绝对禁止"),
            (r"严禁(.+)", "严禁"),
            (r"禁止(.+)", "禁止"),
            (r"不允许(.+)", "不允许"),
            (r"不可以(.+)", "不可以"),
        ],
        
        UserIntentType.GOAL: [
            (r"我的目标[是为：:]\s*(.+)", "目标"),
            (r"我想要(.+)", "想要"),
            (r"我希望(.+)", "希望"),
            (r"我期望(.+)", "期望"),
            (r"目标收益[是为：:]\s*(.+)", "收益目标"),
            (r"月收益目标[是为：:]\s*(.+)", "月目标"),
            (r"年收益目标[是为：:]\s*(.+)", "年目标"),
        ],
        
        UserIntentType.FEEDBACK: [
            (r"太(.+)了", "程度反馈"),
            (r"很(.+)", "程度反馈"),
            (r"非常(.+)", "程度反馈"),
            (r"不够(.+)", "不足反馈"),
            (r"太少了", "数量反馈"),
            (r"太多了", "数量反馈"),
            (r"应该(.+)", "建议"),
            (r"建议(.+)", "建议"),
            (r"最好(.+)", "建议"),
        ],
    }
    
    KEYWORD_WEIGHTS = {
        "关键": 0.9,
        "重要": 0.85,
        "必须": 0.9,
        "一定": 0.85,
        "绝对": 0.95,
        "千万": 0.9,
        "严格": 0.85,
        "永远": 0.9,
        "总是": 0.8,
        "记住": 0.85,
        "记得": 0.8,
        "偏好": 0.75,
        "喜欢": 0.7,
        "习惯": 0.7,
        "风险": 0.8,
        "止损": 0.85,
        "止盈": 0.8,
        "仓位": 0.75,
        "杠杆": 0.8,
        "目标": 0.75,
        "不要": 0.8,
        "禁止": 0.9,
        "避免": 0.75,
    }
    
    @classmethod
    def recognize(cls, user_input: str) -> List[ExtractedIntent]:
        """识别用户输入中的所有意图"""
        intents = []
        
        for intent_type, patterns in cls.PATTERNS.items():
            for pattern, keyword in patterns:
                match = re.search(pattern, user_input, re.IGNORECASE)
                if match:
                    extracted_content = match.group(1) if match.groups() else match.group(0)
                    
                    confidence = cls._calculate_confidence(
                        user_input, extracted_content, keyword, intent_type
                    )
                    
                    keywords = cls._extract_keywords(user_input)
                    
                    intent = ExtractedIntent(
                        intent_type=intent_type,
                        content=extracted_content.strip(),
                        original_text=user_input,
                        confidence=confidence,
                        keywords=keywords,
                        metadata={
                            "pattern": pattern,
                            "matched_keyword": keyword,
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                    
                    intents.append(intent)
        
        if intents:
            intents.sort(key=lambda x: x.confidence, reverse=True)
        
        return intents
    
    @classmethod
    def _calculate_confidence(
        cls, 
        original: str, 
        extracted: str, 
        keyword: str,
        intent_type: UserIntentType
    ) -> float:
        """计算置信度"""
        confidence = 0.5
        
        if keyword in cls.KEYWORD_WEIGHTS:
            confidence = cls.KEYWORD_WEIGHTS[keyword]
        
        if len(extracted) < 5:
            confidence *= 0.8
        elif len(extracted) > 50:
            confidence *= 0.9
        
        for kw, weight in cls.KEYWORD_WEIGHTS.items():
            if kw in original and kw != keyword:
                confidence = min(1.0, confidence + (weight - 0.5) * 0.3)
        
        if intent_type in [UserIntentType.RISK_SETTING, UserIntentType.PROHIBITION]:
            confidence = min(1.0, confidence * 1.1)
        
        return min(1.0, max(0.0, confidence))
    
    @classmethod
    def _extract_keywords(cls, text: str) -> List[str]:
        """提取关键词"""
        keywords = []
        for kw in cls.KEYWORD_WEIGHTS.keys():
            if kw in text:
                keywords.append(kw)
        return keywords
    
    @classmethod
    def extract_preference(cls, user_input: str) -> Optional[Dict[str, Any]]:
        """提取用户偏好"""
        intents = cls.recognize(user_input)
        
        for intent in intents:
            if intent.intent_type == UserIntentType.PREFERENCE:
                return {
                    "type": "preference",
                    "content": intent.content,
                    "confidence": intent.confidence,
                    "keywords": intent.keywords,
                    "original": intent.original_text
                }
        
        return None
    
    @classmethod
    def extract_instruction(cls, user_input: str) -> Optional[Dict[str, Any]]:
        """提取用户指令"""
        intents = cls.recognize(user_input)
        
        for intent in intents:
            if intent.intent_type == UserIntentType.INSTRUCTION:
                return {
                    "type": "instruction",
                    "content": intent.content,
                    "confidence": intent.confidence,
                    "keywords": intent.keywords,
                    "original": intent.original_text
                }
        
        return None
    
    @classmethod
    def extract_risk_setting(cls, user_input: str) -> Optional[Dict[str, Any]]:
        """提取风险设置"""
        intents = cls.recognize(user_input)
        
        for intent in intents:
            if intent.intent_type == UserIntentType.RISK_SETTING:
                return {
                    "type": "risk_setting",
                    "content": intent.content,
                    "confidence": intent.confidence,
                    "keywords": intent.keywords,
                    "original": intent.original_text
                }
        
        return None
    
    @classmethod
    def extract_all_important(cls, user_input: str) -> List[Dict[str, Any]]:
        """提取所有重要信息"""
        intents = cls.recognize(user_input)
        
        return [
            {
                "type": intent.intent_type.value,
                "content": intent.content,
                "confidence": intent.confidence,
                "keywords": intent.keywords,
                "original": intent.original_text
            }
            for intent in intents
            if intent.confidence >= 0.6
        ]
    
    @classmethod
    def should_remember(cls, user_input: str) -> Tuple[bool, float]:
        """判断是否应该记住这条输入"""
        intents = cls.recognize(user_input)
        
        if not intents:
            return False, 0.0
        
        max_confidence = max(intent.confidence for intent in intents)
        
        should_remember = max_confidence >= 0.6
        
        return should_remember, max_confidence


class AutoMemoryRecorder:
    """
    自动记忆记录器
    
    与统一记忆系统集成，自动记录用户指令和偏好
    """
    
    def __init__(self, memory_system=None):
        self.memory = memory_system
        self.recognizer = UserIntentRecognizer
    
    def set_memory_system(self, memory_system):
        """设置记忆系统"""
        self.memory = memory_system
    
    async def process_user_input(self, user_input: str) -> Dict[str, Any]:
        """处理用户输入，自动识别并记录重要信息"""
        result = {
            "recorded": False,
            "intents": [],
            "memory_ids": []
        }
        
        if not self.memory:
            logger.warning("记忆系统未初始化")
            return result
        
        intents = self.recognizer.recognize(user_input)
        
        if not intents:
            return result
        
        result["intents"] = [
            {
                "type": intent.intent_type.value,
                "content": intent.content,
                "confidence": intent.confidence
            }
            for intent in intents
        ]
        
        for intent in intents:
            if intent.confidence >= 0.6:
                memory_id = await self._record_intent(intent)
                if memory_id:
                    result["memory_ids"].append(memory_id)
                    result["recorded"] = True
        
        return result
    
    async def _record_intent(self, intent: ExtractedIntent) -> Optional[str]:
        """记录意图到记忆系统"""
        from .unified_intelligent_memory import UnifiedMemoryType, MemoryPriority
        
        type_mapping = {
            UserIntentType.PREFERENCE: UnifiedMemoryType.USER_PREFERENCE,
            UserIntentType.INSTRUCTION: UnifiedMemoryType.SYSTEM_INSTRUCTION,
            UserIntentType.RISK_SETTING: UnifiedMemoryType.RISK_SETTING,
            UserIntentType.TRADING_RULE: UnifiedMemoryType.SYSTEM_INSTRUCTION,
            UserIntentType.REMINDER: UnifiedMemoryType.SYSTEM_INSTRUCTION,
            UserIntentType.PROHIBITION: UnifiedMemoryType.SYSTEM_INSTRUCTION,
            UserIntentType.GOAL: UnifiedMemoryType.USER_PREFERENCE,
            UserIntentType.FEEDBACK: UnifiedMemoryType.USER_PREFERENCE,
        }
        
        memory_type = type_mapping.get(intent.intent_type, UnifiedMemoryType.USER_PREFERENCE)
        
        if intent.confidence >= 0.85:
            priority = MemoryPriority.CRITICAL
        elif intent.confidence >= 0.75:
            priority = MemoryPriority.HIGH
        else:
            priority = MemoryPriority.NORMAL
        
        summary = f"[{intent.intent_type.value}] {intent.content[:100]}"
        
        return await self.memory.add_memory(
            memory_type=memory_type,
            content=intent.original_text,
            summary=summary,
            metadata={
                "intent_type": intent.intent_type.value,
                "extracted_content": intent.content,
                "confidence": intent.confidence,
                "keywords": intent.keywords
            },
            priority=priority,
            importance=intent.confidence,
            source_module="auto_recorder",
            tags=intent.keywords + [intent.intent_type.value]
        )


user_intent_recognizer = UserIntentRecognizer()
auto_memory_recorder = AutoMemoryRecorder()
