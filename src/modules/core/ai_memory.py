"""
AI智能记忆管理系统 V2.0 - 按需动态加载

核心特性：
1. 固定最小加载 + 按需动态加载
2. 意图识别关键词匹配
3. 30天每日记忆 + 每日自动总结
4. 经验教训永久保留

记忆层级：
- 核心身份层：固定加载（约300字）
- 当日上下文层：固定加载（最近对话）
- 工作记忆层：按需加载（交易、市场、风险）
- 长期经验层：按需加载（经验教训）
"""

import asyncio
import logging
import json
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """记忆类型"""
    CORE_IDENTITY = "core_identity"       # 核心身份（固定加载）
    USER_PREFERENCE = "user_preference"   # 用户偏好
    DAILY_MEMORY = "daily_memory"         # 每日记忆
    DAILY_SUMMARY = "daily_summary"       # 每日总结
    TRADE_RECORD = "trade_record"         # 交易记录
    MARKET_OBSERVATION = "market_observation"  # 市场观察
    RISK_EVENT = "risk_event"             # 风险事件
    EXPERIENCE = "experience"             # 经验教训
    CONVERSATION = "conversation"         # 对话记录


class IntentType(Enum):
    """意图类型"""
    TRADING = "trading"           # 交易相关
    MARKET = "market"             # 市场分析
    RISK = "risk"                 # 风险相关
    LEARNING = "learning"         # 学习总结
    INSTRUCTION = "instruction"   # 工作指令
    CASUAL = "casual"             # 日常对话
    UNKNOWN = "unknown"           # 未知


@dataclass
class IntentKeywords:
    """意图关键词配置"""
    trading: Set[str] = field(default_factory=lambda: {
        "开仓", "平仓", "止损", "止盈", "仓位", "交易", "买卖",
        "入场", "出场", "做多", "做空", "下单", "持仓",
        "加仓", "减仓", "爆仓", "强平", "杠杆",
        "open", "close", "buy", "sell", "long", "short",
        "止盈止损", "移动止损", "分批止盈"
    })
    
    market: Set[str] = field(default_factory=lambda: {
        "行情", "走势", "趋势", "分析", "预测", "涨跌",
        "支撑", "阻力", "突破", "回调", "震荡",
        "牛市", "熊市", "盘整", "反转", "上涨", "下跌",
        "K线", "指标", "RSI", "MACD", "布林带",
        "成交量", "波动率", "市场情绪"
    })
    
    risk: Set[str] = field(default_factory=lambda: {
        "风险", "亏损", "预警", "强平", "危险", "止损",
        "爆仓", "回撤", "损失", "风险控制",
        "仓位过重", "保证金", "杠杆过高",
        "warning", "risk", "danger", "alert"
    })
    
    learning: Set[str] = field(default_factory=lambda: {
        "为什么", "原因", "教训", "改进", "总结", "经验",
        "分析一下", "怎么", "如何", "学习",
        "复盘", "反思", "优化", "调整策略",
        "下次", "以后", "记住"
    })
    
    instruction: Set[str] = field(default_factory=lambda: {
        "你要", "你的职责", "我要求", "我希望", "我全权委托",
        "记住", "以后", "必须", "需要你",
        "我的偏好", "我喜欢", "我不喜欢",
        "设置", "配置", "调整", "修改"
    })


@dataclass
class MemoryItem:
    """记忆条目"""
    memory_id: str
    memory_type: MemoryType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    timestamp: datetime = field(default_factory=datetime.now)
    accessed_count: int = 0


@dataclass
class SmartMemoryConfig:
    """智能记忆配置"""
    core_identity_max_chars: int = 300
    daily_context_max_items: int = 5
    dynamic_memory_max_chars: int = 800
    daily_memory_retention_days: int = 30
    weekly_summary_retention_weeks: int = 12
    enable_auto_summary: bool = True
    summary_time: str = "23:55"


class SmartMemoryManager:
    """
    智能记忆管理器 V2.0
    
    核心特性：
    1. 固定最小加载 - 核心身份（约300字）
    2. 按需动态加载 - 根据意图关键词
    3. 30天每日记忆 + 自动总结
    4. 经验教训永久保留
    """
    
    def __init__(self, config: Optional[SmartMemoryConfig] = None,
                 storage_path: Optional[str] = None,
                 workspace_path: Optional[str] = None):
        self.config = config or SmartMemoryConfig()
        
        if storage_path:
            self.storage_path = Path(storage_path)
        elif workspace_path:
            self.storage_path = Path(workspace_path) / "memory"
        else:
            import os
            base_path = os.environ.get("OPENCLAW_DATA_PATH", "/app/data")
            self.storage_path = Path(base_path) / "memory"
        
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            import os
            fallback = Path("/tmp/openclaw_memory")
            fallback.mkdir(parents=True, exist_ok=True)
            self.storage_path = fallback
            logger.warning(f"记忆存储路径权限不足，使用备用路径: {fallback}")
        
        self.workspace_path = Path(workspace_path) if workspace_path else Path("workspace")
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        
        self.intent_keywords = IntentKeywords()
        
        self.workspace_memory: Dict[str, str] = {}
        self.daily_memory_cache: Dict[str, str] = {}
        self.conversation_history: List[Dict[str, Any]] = []
        
        self.memory_files = [
            "SOUL.md",
            "IDENTITY.md",
            "USER.md",
            "INSTRUCTIONS.md",
            "TRADING.md"
        ]
        
        self._load_workspace_memory()
        self._load_conversation_history()
        
        self._stats = {
            "total_queries": 0,
            "intent_distribution": {intent.value: 0 for intent in IntentType},
            "memory_loads": {
                "core": 0,
                "trading": 0,
                "market": 0,
                "risk": 0,
                "learning": 0,
                "instruction": 0
            }
        }
        
        logger.info("✅ 智能记忆管理器V2.0初始化完成")
    
    async def initialize(self) -> bool:
        """异步初始化"""
        self._ensure_memory_structure()
        return True
    
    def _ensure_memory_structure(self):
        """确保记忆目录结构存在"""
        dirs = [
            self.storage_path / "daily",
            self.storage_path / "summary",
            self.storage_path / "weekly",
            self.storage_path / "monthly",
            self.storage_path / "experience",
            self.storage_path / "trades",
            self.storage_path / "sessions"
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
    
    def _load_workspace_memory(self):
        """加载工作区记忆文件"""
        for filename in self.memory_files:
            file_path = self.workspace_path / filename
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        self.workspace_memory[filename] = f.read()
                    logger.debug(f"📄 加载记忆文件: {filename}")
                except Exception as e:
                    logger.error(f"加载记忆文件 {filename} 失败: {e}")
    
    def _load_conversation_history(self):
        """加载对话历史"""
        try:
            history_file = self.storage_path / "conversation_history.json"
            if history_file.exists():
                with open(history_file, "r", encoding="utf-8") as f:
                    self.conversation_history = json.load(f)
        except Exception as e:
            logger.warning(f"加载对话历史失败: {e}")
            self.conversation_history = []
    
    def _save_conversation_history(self):
        """保存对话历史"""
        try:
            history_file = self.storage_path / "conversation_history.json"
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(self.conversation_history[-100:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存对话历史失败: {e}")
    
    def analyze_intent(self, user_input: str) -> IntentType:
        """
        分析用户输入的意图
        
        Args:
            user_input: 用户输入内容
            
        Returns:
            意图类型
        """
        user_input_lower = user_input.lower()
        intent_scores: Dict[IntentType, int] = {}
        
        for intent_type in [IntentType.TRADING, IntentType.MARKET, 
                           IntentType.RISK, IntentType.LEARNING, 
                           IntentType.INSTRUCTION]:
            keywords = getattr(self.intent_keywords, intent_type.value, set())
            score = sum(1 for kw in keywords if kw in user_input_lower)
            if score > 0:
                intent_scores[intent_type] = score
        
        if not intent_scores:
            return IntentType.CASUAL
        
        max_score = max(intent_scores.values())
        top_intents = [k for k, v in intent_scores.items() if v == max_score]
        
        priority_order = [
            IntentType.RISK,
            IntentType.INSTRUCTION,
            IntentType.TRADING,
            IntentType.LEARNING,
            IntentType.MARKET
        ]
        
        for intent in priority_order:
            if intent in top_intents:
                return intent
        
        return top_intents[0] if top_intents else IntentType.CASUAL
    
    def build_memory_context(self, user_input: str) -> str:
        """
        智能构建记忆上下文
        
        加载策略：
        1. 固定加载：核心身份（约300字）
        2. 固定加载：最近对话上下文（3-5条）
        3. 按需加载：根据意图动态加载
        
        Args:
            user_input: 用户输入
            
        Returns:
            记忆上下文字符串
        """
        self._stats["total_queries"] += 1
        
        context_parts = []
        
        core_context = self._build_core_identity_context()
        if core_context:
            context_parts.append(core_context)
            self._stats["memory_loads"]["core"] += 1
        
        conversation_context = self._build_conversation_context()
        if conversation_context:
            context_parts.append(conversation_context)
        
        intent = self.analyze_intent(user_input)
        self._stats["intent_distribution"][intent.value] += 1
        
        dynamic_context = self._build_dynamic_context(intent, user_input)
        if dynamic_context:
            context_parts.append(dynamic_context)
        
        if context_parts:
            return "\n\n".join(context_parts)
        return ""
    
    def _build_core_identity_context(self) -> str:
        """构建核心身份上下文（固定加载，约300字）"""
        parts = []
        
        if "IDENTITY.md" in self.workspace_memory:
            identity = self._extract_key_content(
                self.workspace_memory["IDENTITY.md"],
                ["专业操盘手", "交易专家", "全权负责", "快速盈利"]
            )
            if identity:
                parts.append(f"[身份] {identity}")
        
        if "USER.md" in self.workspace_memory:
            user_info = self._extract_key_content(
                self.workspace_memory["USER.md"],
                ["全权委托", "快速盈利", "不需要参与", "交易偏好"]
            )
            if user_info:
                parts.append(f"[用户期望] {user_info}")
        
        if "SOUL.md" in self.workspace_memory:
            soul = self._extract_key_content(
                self.workspace_memory["SOUL.md"],
                ["主动性", "专业性", "判断"]
            )
            if soul:
                parts.append(f"[核心原则] {soul}")
        
        context = "\n".join(parts)
        
        if len(context) > self.config.core_identity_max_chars:
            context = context[:self.config.core_identity_max_chars] + "..."
        
        return context
    
    def _extract_key_content(self, content: str, keywords: List[str]) -> str:
        """提取包含关键词的关键内容"""
        lines = content.split("\n")
        key_lines = []
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for kw in keywords:
                if kw in line:
                    key_lines.append(line)
                    break
        
        if key_lines:
            return "；".join(key_lines[:3])
        
        clean_lines = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
        return "；".join(clean_lines[:2]) if clean_lines else ""
    
    def _build_conversation_context(self) -> str:
        """构建对话上下文（最近3-5条）"""
        if not self.conversation_history:
            return ""
        
        recent = self.conversation_history[-self.config.daily_context_max_items:]
        if not recent:
            return ""
        
        parts = []
        for item in recent:
            role = item.get("role", "user")
            content = item.get("content", "")
            if content:
                preview = content[:100] + "..." if len(content) > 100 else content
                parts.append(f"[{role}] {preview}")
        
        if parts:
            return "[最近对话]\n" + "\n".join(parts)
        return ""
    
    def _build_dynamic_context(self, intent: IntentType, user_input: str) -> str:
        """根据意图构建动态上下文"""
        parts = []
        
        if intent == IntentType.TRADING:
            context = self._load_trading_context()
            if context:
                parts.append(context)
                self._stats["memory_loads"]["trading"] += 1
        
        elif intent == IntentType.MARKET:
            context = self._load_market_context()
            if context:
                parts.append(context)
                self._stats["memory_loads"]["market"] += 1
        
        elif intent == IntentType.RISK:
            context = self._load_risk_context()
            if context:
                parts.append(context)
                self._stats["memory_loads"]["risk"] += 1
        
        elif intent == IntentType.LEARNING:
            context = self._load_experience_context()
            if context:
                parts.append(context)
                self._stats["memory_loads"]["learning"] += 1
        
        elif intent == IntentType.INSTRUCTION:
            context = self._load_instruction_context()
            if context:
                parts.append(context)
                self._stats["memory_loads"]["instruction"] += 1
        
        if intent in [IntentType.TRADING, IntentType.MARKET, IntentType.RISK]:
            today_summary = self._load_today_summary()
            if today_summary:
                parts.append(today_summary)
        
        result = "\n\n".join(parts)
        
        if len(result) > self.config.dynamic_memory_max_chars:
            result = result[:self.config.dynamic_memory_max_chars] + "..."
        
        return result
    
    def _load_trading_context(self) -> str:
        """加载交易相关上下文"""
        parts = []
        
        if "TRADING.md" in self.workspace_memory:
            trading = self.workspace_memory["TRADING.md"][:300]
            parts.append(f"[交易规则]\n{trading}")
        
        today_trades = self._get_today_trades()
        if today_trades:
            parts.append(f"[今日交易]\n{today_trades}")
        
        return "\n\n".join(parts) if parts else ""
    
    def _load_market_context(self) -> str:
        """加载市场相关上下文"""
        parts = []
        
        today_market = self._get_today_market_observations()
        if today_market:
            parts.append(f"[今日市场观察]\n{today_market}")
        
        return "\n\n".join(parts) if parts else ""
    
    def _load_risk_context(self) -> str:
        """加载风险相关上下文"""
        parts = []
        
        risk_events = self._get_recent_risk_events()
        if risk_events:
            parts.append(f"[近期风险事件]\n{risk_events}")
        
        return "\n\n".join(parts) if parts else ""
    
    def _load_experience_context(self) -> str:
        """加载经验教训上下文"""
        parts = []
        
        experience_file = self.storage_path / "experience" / "lessons_learned.md"
        if experience_file.exists():
            try:
                with open(experience_file, "r", encoding="utf-8") as f:
                    content = f.read()[:400]
                    parts.append(f"[经验教训]\n{content}")
            except:
                pass
        
        return "\n\n".join(parts) if parts else ""
    
    def _load_instruction_context(self) -> str:
        """加载工作指令上下文"""
        parts = []
        
        if "INSTRUCTIONS.md" in self.workspace_memory:
            instructions = self.workspace_memory["INSTRUCTIONS.md"][:400]
            parts.append(f"[工作指令]\n{instructions}")
        
        return "\n\n".join(parts) if parts else ""
    
    def _load_today_summary(self) -> str:
        """加载今日总结"""
        today = datetime.now().strftime("%Y-%m-%d")
        summary_file = self.storage_path / "summary" / f"{today}.md"
        
        if summary_file.exists():
            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    return f"[今日总结]\n{f.read()[:300]}"
            except:
                pass
        
        return ""
    
    def _get_today_trades(self) -> str:
        """获取今日交易记录"""
        today = datetime.now().strftime("%Y-%m-%d")
        trades_file = self.storage_path / "trades" / f"{today}.json"
        
        if trades_file.exists():
            try:
                with open(trades_file, "r", encoding="utf-8") as f:
                    trades = json.load(f)
                    if trades:
                        lines = []
                        for t in trades[-3:]:
                            lines.append(f"- {t.get('symbol', '')} {t.get('action', '')} @ {t.get('price', '')}")
                        return "\n".join(lines)
            except:
                pass
        
        return ""
    
    def _get_today_market_observations(self) -> str:
        """获取今日市场观察"""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = self.storage_path / "daily" / f"{today}.md"
        
        if daily_file.exists():
            try:
                with open(daily_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    market_section = self._extract_section(content, "市场发现")
                    if market_section:
                        return market_section[:200]
            except:
                pass
        
        return ""
    
    def _get_recent_risk_events(self) -> str:
        """获取近期风险事件"""
        parts = []
        
        for i in range(3):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_file = self.storage_path / "daily" / f"{date}.md"
            
            if daily_file.exists():
                try:
                    with open(daily_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        risk_section = self._extract_section(content, "风险")
                        if risk_section:
                            parts.append(f"[{date}] {risk_section[:100]}")
                except:
                    pass
        
        return "\n".join(parts) if parts else ""
    
    def _extract_section(self, content: str, section_name: str) -> str:
        """从内容中提取特定章节"""
        pattern = rf"##\s*.*{section_name}.*\n([\s\S]*?)(?=##|$)"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
    
    def add_message(self, role: str, content: str) -> None:
        """
        添加对话消息
        
        Args:
            role: 角色 (user/assistant)
            content: 消息内容
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        self.conversation_history.append(message)
        
        while len(self.conversation_history) > 100:
            self.conversation_history.pop(0)
        
        self._save_conversation_history()
        
        if role == "user":
            self._process_user_message(content)
    
    def _process_user_message(self, content: str):
        """处理用户消息，提取重要信息"""
        intent = self.analyze_intent(content)
        
        if intent == IntentType.INSTRUCTION:
            self._extract_user_preference(content)
        
        elif intent == IntentType.LEARNING:
            self._extract_experience(content)
    
    def _extract_user_preference(self, content: str):
        """提取用户偏好"""
        preference_patterns = [
            r"我(希望|要求|偏好|喜欢)\s*[：:]?\s*(.+)",
            r"我的(偏好|风格|要求)\s*[：:]?\s*(.+)",
            r"(记住|以后)\s*[：:]?\s*(.+)"
        ]
        
        for pattern in preference_patterns:
            match = re.search(pattern, content)
            if match:
                preference = match.group(2).strip()
                self._save_preference(preference)
                break
    
    def _save_preference(self, preference: str):
        """保存用户偏好"""
        try:
            pref_file = self.storage_path / "user_preferences.json"
            
            prefs = []
            if pref_file.exists():
                with open(pref_file, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
            
            prefs.append({
                "content": preference,
                "timestamp": datetime.now().isoformat()
            })
            
            with open(pref_file, "w", encoding="utf-8") as f:
                json.dump(prefs[-50:], f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存用户偏好失败: {e}")
    
    def _extract_experience(self, content: str):
        """提取经验教训"""
        experience_patterns = [
            r"教训\s*[：:]?\s*(.+)",
            r"原因\s*[：:]?\s*(.+)",
            r"改进\s*[：:]?\s*(.+)",
            r"下次\s*[：:]?\s*(.+)"
        ]
        
        for pattern in experience_patterns:
            match = re.search(pattern, content)
            if match:
                experience = match.group(1).strip()
                self._save_experience(experience)
                break
    
    def _save_experience(self, experience: str):
        """保存经验教训"""
        try:
            exp_file = self.storage_path / "experience" / "lessons_learned.md"
            
            existing = ""
            if exp_file.exists():
                with open(exp_file, "r", encoding="utf-8") as f:
                    existing = f.read()
            
            new_entry = f"\n- [{datetime.now().strftime('%Y-%m-%d %H:%M')}] {experience}"
            
            with open(exp_file, "w", encoding="utf-8") as f:
                f.write(existing + new_entry)
                
        except Exception as e:
            logger.error(f"保存经验教训失败: {e}")
    
    async def record_trade(self, trade: Dict[str, Any]):
        """记录交易"""
        today = datetime.now().strftime("%Y-%m-%d")
        trades_file = self.storage_path / "trades" / f"{today}.json"
        
        try:
            trades = []
            if trades_file.exists():
                with open(trades_file, "r", encoding="utf-8") as f:
                    trades = json.load(f)
            
            trade["timestamp"] = datetime.now().isoformat()
            trades.append(trade)
            
            with open(trades_file, "w", encoding="utf-8") as f:
                json.dump(trades, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"记录交易失败: {e}")
    
    async def record_market_observation(self, observation: str):
        """记录市场观察"""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = self.storage_path / "daily" / f"{today}.md"
        
        try:
            existing = ""
            if daily_file.exists():
                with open(daily_file, "r", encoding="utf-8") as f:
                    existing = f.read()
            
            if "## 市场发现" not in existing:
                existing += "\n\n## 市场发现\n"
            
            time_str = datetime.now().strftime("%H:%M")
            new_entry = f"\n- [{time_str}] {observation}"
            
            with open(daily_file, "w", encoding="utf-8") as f:
                f.write(existing + new_entry)
                
        except Exception as e:
            logger.error(f"记录市场观察失败: {e}")
    
    async def record_risk_event(self, event: str, level: str = "warning"):
        """记录风险事件"""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = self.storage_path / "daily" / f"{today}.md"
        
        try:
            existing = ""
            if daily_file.exists():
                with open(daily_file, "r", encoding="utf-8") as f:
                    existing = f.read()
            
            if "## 风险事件" not in existing:
                existing += "\n\n## 风险事件\n"
            
            time_str = datetime.now().strftime("%H:%M")
            emoji = "⚠️" if level == "warning" else "🚨"
            new_entry = f"\n- [{time_str}] {emoji} {event}"
            
            with open(daily_file, "w", encoding="utf-8") as f:
                f.write(existing + new_entry)
                
        except Exception as e:
            logger.error(f"记录风险事件失败: {e}")
    
    async def generate_daily_summary(self) -> str:
        """生成每日总结"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        trades = self._get_all_today_trades()
        market_obs = self._get_all_today_observations()
        risk_events = self._get_all_today_risks()
        
        total_trades = len(trades)
        profit_trades = [t for t in trades if t.get("pnl", 0) > 0]
        loss_trades = [t for t in trades if t.get("pnl", 0) < 0]
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        win_rate = len(profit_trades) / total_trades * 100 if total_trades > 0 else 0
        
        summary = f"""# {today} 交易总结

## 📊 交易统计
- 总交易次数：{total_trades}笔
- 盈利交易：{len(profit_trades)}笔
- 亏损交易：{len(loss_trades)}笔
- 胜率：{win_rate:.1f}%
- 总盈亏：{total_pnl:+.2f} USDT

## 📈 今日交易记录
"""
        
        for t in trades:
            summary += f"- {t.get('symbol', '')} {t.get('action', '')} @ {t.get('price', '')} | PnL: {t.get('pnl', 0):+.2f}\n"
        
        if market_obs:
            summary += "\n## 💡 市场发现\n"
            for obs in market_obs:
                summary += f"- {obs}\n"
        
        if risk_events:
            summary += "\n## ⚠️ 风险事件\n"
            for event in risk_events:
                summary += f"- {event}\n"
        
        summary += "\n## 📝 明日计划\n- [待补充]\n"
        
        summary_file = self.storage_path / "summary" / f"{today}.md"
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(summary)
        
        logger.info(f"✅ 生成每日总结: {summary_file}")
        
        return summary
    
    def _get_all_today_trades(self) -> List[Dict]:
        """获取今日所有交易"""
        today = datetime.now().strftime("%Y-%m-%d")
        trades_file = self.storage_path / "trades" / f"{today}.json"
        
        if trades_file.exists():
            try:
                with open(trades_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def _get_all_today_observations(self) -> List[str]:
        """获取今日所有市场观察"""
        observations = []
        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = self.storage_path / "daily" / f"{today}.md"
        
        if daily_file.exists():
            try:
                with open(daily_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    section = self._extract_section(content, "市场发现")
                    if section:
                        for line in section.split("\n"):
                            if line.strip().startswith("-"):
                                observations.append(line.strip()[1:].strip())
            except:
                pass
        return observations
    
    def _get_all_today_risks(self) -> List[str]:
        """获取今日所有风险事件"""
        risks = []
        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = self.storage_path / "daily" / f"{today}.md"
        
        if daily_file.exists():
            try:
                with open(daily_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    section = self._extract_section(content, "风险")
                    if section:
                        for line in section.split("\n"):
                            if line.strip().startswith("-"):
                                risks.append(line.strip()[1:].strip())
            except:
                pass
        return risks
    
    async def cleanup_old_memories(self):
        """清理过期记忆"""
        cutoff_date = datetime.now() - timedelta(days=self.config.daily_memory_retention_days)
        
        daily_dir = self.storage_path / "daily"
        if daily_dir.exists():
            for file in daily_dir.glob("*.md"):
                try:
                    date_str = file.stem
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if file_date < cutoff_date:
                        file.unlink()
                        logger.debug(f"清理过期记忆: {file}")
                except:
                    pass
        
        summary_dir = self.storage_path / "summary"
        if summary_dir.exists():
            for file in summary_dir.glob("*.md"):
                try:
                    date_str = file.stem
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if file_date < cutoff_date:
                        file.unlink()
                        logger.debug(f"清理过期总结: {file}")
                except:
                    pass
        
        logger.info(f"✅ 清理 {self.config.daily_memory_retention_days} 天前的记忆")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_queries": self._stats["total_queries"],
            "intent_distribution": self._stats["intent_distribution"],
            "memory_loads": self._stats["memory_loads"],
            "conversation_history_count": len(self.conversation_history),
            "workspace_files_loaded": list(self.workspace_memory.keys())
        }
    
    async def cleanup(self):
        """清理资源"""
        self._save_conversation_history()
        logger.info("智能记忆管理器清理完成")


def create_smart_memory_manager(
    storage_path: Optional[str] = None,
    workspace_path: Optional[str] = None
) -> SmartMemoryManager:
    """创建智能记忆管理器实例"""
    return SmartMemoryManager(
        storage_path=storage_path,
        workspace_path=workspace_path
    )
