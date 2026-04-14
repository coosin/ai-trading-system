"""
用户指令智能识别器 - 增强版
参照正常AI对话模式，实现深层语义理解
"""
import re
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from src.modules.memory.memory_schema import base_metadata, kind_tag, symbol_tag, tags


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
    AUTHORIZATION = "authorization"
    BLACKLIST = "blacklist"
    WORK_DUTY = "work_duty"


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
    用户意图识别器 - 增强版
    
    参照正常AI对话模式，实现：
    1. 深层语义理解 - 不只匹配关键词，理解句子含义
    2. 上下文关联 - 结合历史记忆理解当前输入
    3. 多意图识别 - 一句话可能包含多个意图
    4. 意图优先级 - 区分核心意图和次要意图
    """
    
    SEMANTIC_PATTERNS = {
        UserIntentType.BLACKLIST: [
            (r"(.+?)是(.+?)的禁区", "禁区定义"),
            (r"(.+?)属于禁区", "禁区声明"),
            (r"(.+?)不用你(.+?)", "排除责任"),
            (r"(.+?)由我(.+?)", "自主负责"),
            (r"(.+?)我自己(.+?)", "自主操作"),
            (r"除了(.+?)之外", "排除范围"),
            (r"(.+?)不要操作", "禁止操作"),
            (r"(.+?)不要管", "禁止管理"),
            (r"(.+?)不要处理", "禁止处理"),
            (r"(.+?)是黑名单", "黑名单定义"),
            (r"把(.+?)加入黑名单", "添加黑名单"),
            (r"(.+?)禁止交易", "交易禁止"),
        ],
        
        UserIntentType.AUTHORIZATION: [
            (r"全权负责", "完全授权"),
            (r"整个交易流程(.+?)负责", "流程授权"),
            (r"你自己(.+?)", "自主决策"),
            (r"自动(.+?)", "自动执行"),
            (r"自主(.+?)", "自主行动"),
            (r"不需要提醒", "主动工作"),
            (r"根本不需要提醒", "主动职责"),
            (r"这是你的工作", "职责定义"),
            (r"你的职责是(.+?)", "职责明确"),
            (r"交易流程你全权负责", "交易全权"),
            (r"开平仓(.+?)都是你负责", "操作授权"),
        ],
        
        UserIntentType.WORK_DUTY: [
            (r"策略(.+?)随时(.+?)优化", "策略优化职责"),
            (r"随时跟踪(.+?)市场", "市场跟踪职责"),
            (r"抓住机遇", "机会捕捉职责"),
            (r"主动寻找(.+?)机会", "主动寻找职责"),
            (r"自动进行(.+?)工作", "自动工作"),
            (r"这是你就要自动进行的工作", "自动职责"),
            (r"你的工作必须做好", "工作要求"),
            (r"根据市场(.+?)自主(.+?)", "自主决策"),
            (r"随时把控(.+?)动向", "动态监控"),
        ],
        
        UserIntentType.PREFERENCE: [
            (r"我(比较|更|最)?喜欢(.+)", "喜欢"),
            (r"我(比较|更|最)?偏好(.+)", "偏好"),
            (r"我(通常|一般|习惯)(.+)", "习惯"),
            (r"我倾向于(.+)", "倾向"),
            (r"我更倾向于(.+)", "倾向"),
            (r"我主要交易(.+)", "交易偏好"),
            (r"我擅长(.+)", "擅长"),
            (r"我的风格是(.+)", "风格定义"),
            (r"我习惯(.+)", "习惯"),
        ],
        
        UserIntentType.INSTRUCTION: [
            (r"记住[：:]?\s*(.+)", "记住"),
            (r"记得[：:]?\s*(.+)", "记得"),
            (r"请记住(.+)", "记住"),
            (r"要记住(.+)", "记住"),
            (r"记住了吗", "确认记住"),
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
            (r"唯一要求(.+)", "核心要求"),
            (r"我只要求(.+)", "核心要求"),
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
            (r"听不懂吗(.+)", "强调禁止"),
            (r"怎么听不明白(.+)", "强调理解"),
        ],
        
        UserIntentType.GOAL: [
            (r"我的目标[是为：:]\s*(.+)", "目标"),
            (r"我想要(.+)", "想要"),
            (r"我希望(.+)", "希望"),
            (r"我期望(.+)", "期望"),
            (r"目标收益[是为：:]\s*(.+)", "收益目标"),
            (r"月收益目标[是为：:]\s*(.+)", "月目标"),
            (r"年收益目标[是为：:]\s*(.+)", "年目标"),
            (r"赶紧盈利", "盈利目标"),
            (r"保证盈利", "盈利要求"),
            (r"快速盈利", "快速盈利"),
            (r"增长资本", "资本增长"),
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
            (r"听不懂", "理解问题"),
            (r"不明白", "理解问题"),
            (r"智力障碍", "能力质疑"),
        ],
    }
    
    KEYWORD_WEIGHTS = {
        "禁区": 0.95,
        "黑名单": 0.95,
        "全权": 0.9,
        "自主": 0.85,
        "自动": 0.85,
        "主动": 0.85,
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
        "盈利": 0.85,
        "职责": 0.8,
        "工作": 0.75,
        "负责": 0.8,
        "跟踪": 0.7,
        "监控": 0.7,
        "策略": 0.75,
        "优化": 0.75,
        "开仓": 0.8,
        "平仓": 0.8,
        "交易": 0.75,
    }
    
    CONTEXTUAL_BOOSTS = {
        "强调语气": ["听不懂", "不明白", "再次", "反复", "怎么还", "说了多少次"],
        "紧急程度": ["赶紧", "立即", "马上", "快速", "紧急"],
        "否定强化": ["不要", "不用", "不用管", "不需要"],
    }
    
    @classmethod
    def recognize(cls, user_input: str) -> List[ExtractedIntent]:
        """识别用户输入中的所有意图 - 增强版"""
        intents = []
        
        for intent_type, patterns in cls.SEMANTIC_PATTERNS.items():
            for pattern, keyword in patterns:
                match = re.search(pattern, user_input, re.IGNORECASE)
                if match:
                    if match.groups():
                        extracted_content = match.group(1) if len(match.groups()) == 1 else " ".join(match.groups())
                    else:
                        extracted_content = match.group(0)
                    
                    confidence = cls._calculate_confidence_enhanced(
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
            unique_intents = []
            seen_types = set()
            for intent in intents:
                if intent.intent_type not in seen_types:
                    unique_intents.append(intent)
                    seen_types.add(intent.intent_type)
            
            return unique_intents
        
        return intents
    
    @classmethod
    def _calculate_confidence_enhanced(
        cls, 
        original: str, 
        extracted: str, 
        keyword: str,
        intent_type: UserIntentType
    ) -> float:
        """增强版置信度计算"""
        confidence = 0.5
        
        if keyword in cls.KEYWORD_WEIGHTS:
            confidence = cls.KEYWORD_WEIGHTS[keyword]
        
        for boost_type, boost_words in cls.CONTEXTUAL_BOOSTS.items():
            for word in boost_words:
                if word in original:
                    confidence = min(1.0, confidence + 0.1)
        
        if len(extracted) < 5:
            confidence *= 0.8
        elif len(extracted) > 50:
            confidence *= 0.95
        
        for kw, weight in cls.KEYWORD_WEIGHTS.items():
            if kw in original and kw != keyword:
                confidence = min(1.0, confidence + (weight - 0.5) * 0.2)
        
        high_priority_types = [
            UserIntentType.BLACKLIST, 
            UserIntentType.AUTHORIZATION,
            UserIntentType.PROHIBITION
        ]
        if intent_type in high_priority_types:
            confidence = min(1.0, confidence * 1.1)
        
        emphasis_patterns = [
            r"听不懂吗",
            r"怎么.*不明白",
            r"再次强调",
            r"说了.*次",
            r"根本不需要",
        ]
        for pattern in emphasis_patterns:
            if re.search(pattern, original):
                confidence = min(1.0, confidence + 0.15)
                break
        
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
    def extract_blacklist_items(cls, user_input: str) -> List[Dict[str, Any]]:
        """提取黑名单项目"""
        blacklist_items = []
        
        patterns = [
            (r"以太坊|ETH", "ETH/USDT", "交易对黑名单"),
            (r"比特币|BTC", "BTC/USDT", "交易对黑名单"),
            (r"(\w+/USDT)是禁区", None, "交易对黑名单"),
            (r"(\w+)属于禁区", None, "交易对黑名单"),
        ]
        
        for pattern, default_symbol, reason in patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                symbol = default_symbol or match.group(1)
                if not symbol.endswith('/USDT') and not symbol.endswith('/USDT'):
                    symbol = symbol.upper() + '/USDT'
                blacklist_items.append({
                    "symbol": symbol,
                    "reason": reason,
                    "original_text": user_input
                })
        
        return blacklist_items
    
    @classmethod
    def extract_authorization_scope(cls, user_input: str) -> Dict[str, Any]:
        """提取授权范围"""
        authorization = {
            "full_authorization": True,
            "auto_trading": True,
            "auto_strategy": True,
            "excluded_symbols": [],
            "included_symbols": [],
        }
        
        if re.search(r"全权负责|整个交易流程.*负责", user_input):
            authorization["full_authorization"] = True
            authorization["auto_trading"] = True
            authorization["auto_strategy"] = True
        
        if re.search(r"自动|自主|你自己", user_input):
            authorization["auto_trading"] = True
        
        if re.search(r"策略.*优化|自动.*策略", user_input):
            authorization["auto_strategy"] = True
        
        exclude_match = re.search(r"除了?([^，。]+)之外", user_input)
        if exclude_match:
            excluded = exclude_match.group(1)
            if "以太坊" in excluded or "ETH" in excluded:
                authorization["excluded_symbols"].append("ETH/USDT")
        
        return authorization
    
    @classmethod
    def extract_work_duties(cls, user_input: str) -> List[Dict[str, Any]]:
        """提取工作职责"""
        duties = []
        
        duty_patterns = [
            (r"策略.*优化", "策略优化", "自动优化交易策略"),
            (r"跟踪.*市场", "市场跟踪", "实时监控市场动态"),
            (r"抓住.*机遇|寻找.*机会", "机会捕捉", "主动发现交易机会"),
            (r"开仓|平仓", "交易执行", "执行开仓平仓操作"),
            (r"策略.*开发", "策略开发", "开发新的交易策略"),
            (r"回测", "策略回测", "对策略进行回测验证"),
        ]
        
        for pattern, duty_name, duty_desc in duty_patterns:
            if re.search(pattern, user_input):
                duties.append({
                    "name": duty_name,
                    "description": duty_desc,
                    "auto": "自动" in user_input or "自主" in user_input or "不需要提醒" in user_input
                })
        
        return duties
    
    @classmethod
    def should_remember(cls, user_input: str) -> Tuple[bool, float]:
        """判断是否应该记住这条输入"""
        intents = cls.recognize(user_input)
        
        if not intents:
            return False, 0.0
        
        max_confidence = max(intent.confidence for intent in intents)
        
        should_remember = max_confidence >= 0.6
        
        return should_remember, max_confidence
    
    @classmethod
    def get_intent_summary(cls, user_input: str) -> Dict[str, Any]:
        """获取意图摘要 - 用于AI理解"""
        intents = cls.recognize(user_input)
        blacklist = cls.extract_blacklist_items(user_input)
        authorization = cls.extract_authorization_scope(user_input)
        duties = cls.extract_work_duties(user_input)
        
        return {
            "intents": [
                {
                    "type": intent.intent_type.value,
                    "content": intent.content,
                    "confidence": intent.confidence,
                    "keywords": intent.keywords
                }
                for intent in intents
            ],
            "blacklist": blacklist,
            "authorization": authorization,
            "duties": duties,
            "should_remember": any(intent.confidence >= 0.6 for intent in intents),
            "importance_level": "critical" if any(intent.confidence >= 0.9 for intent in intents) else 
                               "high" if any(intent.confidence >= 0.8 for intent in intents) else "normal"
        }


class AutoMemoryRecorder:
    """
    自动记忆记录器 - 增强版
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
            "memory_ids": [],
            "blacklist_updated": False,
            "authorization_updated": False
        }
        
        if not self.memory:
            logger.warning("记忆系统未初始化")
            return result
        
        intent_summary = self.recognizer.get_intent_summary(user_input)
        
        result["intents"] = intent_summary["intents"]
        
        if intent_summary["blacklist"]:
            for item in intent_summary["blacklist"]:
                memory_id = await self._record_blacklist(item)
                if memory_id:
                    result["memory_ids"].append(memory_id)
                    result["blacklist_updated"] = True
                    result["recorded"] = True
        
        if intent_summary["authorization"]["full_authorization"]:
            memory_id = await self._record_authorization(intent_summary["authorization"], user_input)
            if memory_id:
                result["memory_ids"].append(memory_id)
                result["authorization_updated"] = True
                result["recorded"] = True
        
        for intent_data in intent_summary["intents"]:
            if intent_data["confidence"] >= 0.6:
                memory_id = await self._record_intent_from_data(intent_data, user_input)
                if memory_id:
                    result["memory_ids"].append(memory_id)
                    result["recorded"] = True
        
        return result
    
    async def _record_blacklist(self, item: Dict[str, Any]) -> Optional[str]:
        """记录黑名单"""
        sym = item.get("symbol")
        return await self.memory.add_memory(
            memory_type="trading_rule",
            content=f"黑名单: {item['symbol']} - {item['reason']}",
            summary=f"🚫 交易对黑名单: {item['symbol']}",
            metadata=base_metadata(
                source_module="intent_recognizer",
                kind="blacklist",
                symbol=sym,
                extra={"type": "blacklist", "reason": item.get("reason"), "auto_recorded": True},
            ),
            importance=1.0,
            source_module="intent_recognizer",
            tags=tags(kind_tag("blacklist"), symbol_tag(sym)),
        )
    
    async def _record_authorization(self, auth: Dict[str, Any], original: str) -> Optional[str]:
        """记录授权"""
        return await self.memory.add_memory(
            memory_type="trading_rule",
            content=f"交易授权: 全权负责={auth['full_authorization']}, 自动交易={auth['auto_trading']}, 排除={auth['excluded_symbols']}",
            summary=f"✅ 交易授权: {'全权负责' if auth['full_authorization'] else '部分授权'}",
            metadata=base_metadata(
                source_module="intent_recognizer",
                kind="authorization",
                extra={
                    "type": "authorization",
                    "full_authorization": auth.get("full_authorization"),
                    "auto_trading": auth.get("auto_trading"),
                    "excluded_symbols": auth.get("excluded_symbols"),
                    "auto_recorded": True,
                },
            ),
            importance=0.95,
            source_module="intent_recognizer",
            tags=tags(kind_tag("authorization"), kind_tag("trading")),
        )
    
    async def _record_intent_from_data(self, intent_data: Dict[str, Any], original: str) -> Optional[str]:
        """从意图数据记录"""
        type_mapping = {
            "preference": "user_preference",
            "instruction": "trading_rule",
            "risk_setting": "risk_event",
            "trading_rule": "trading_rule",
            "reminder": "trading_rule",
            "prohibition": "trading_rule",
            "goal": "user_preference",
            "feedback": "user_preference",
            "blacklist": "trading_rule",
            "authorization": "trading_rule",
            "work_duty": "trading_rule",
        }
        
        intent_type = intent_data["type"]
        memory_type = type_mapping.get(intent_type, "user_preference")
        
        confidence = intent_data["confidence"]
        if confidence >= 0.9:
            priority = "critical"
        elif confidence >= 0.8:
            priority = "high"
        else:
            priority = "normal"
        
        return await self.memory.add_memory(
            memory_type=memory_type,
            content=original,
            summary=f"[{intent_type}] {intent_data['content'][:100]}",
            metadata=base_metadata(
                source_module="intent_recognizer",
                kind=f"intent:{intent_type}",
                extra={
                    "intent_type": intent_type,
                    "confidence": confidence,
                    "keywords": intent_data.get("keywords", []),
                    "auto_recorded": True,
                    "priority": priority,
                },
            ),
            importance=confidence,
            source_module="intent_recognizer",
            tags=tags(
                kind_tag("intent"),
                kind_tag(intent_type),
                extra=list(intent_data.get("keywords", []) or []),
            ),
        )


user_intent_recognizer = UserIntentRecognizer()
auto_memory_recorder = AutoMemoryRecorder()
