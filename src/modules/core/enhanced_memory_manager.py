"""
增强记忆管理器 - 参考 OpenClaw 架构

核心改进：
1. 智能识别重要信息并自动保存到长期记忆
2. 会话管理和对话历史
3. 记忆自动压缩和摘要
4. 工作区文件热更新
"""

import asyncio
import json
import logging
import re
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryPriority(Enum):
    """记忆优先级"""
    CRITICAL = 0    # 关键记忆，永久保留（用户偏好、风险设置）
    HIGH = 1        # 高优先级（重要决策、交易记录）
    NORMAL = 2      # 普通优先级（日常对话）
    LOW = 3         # 低优先级（临时信息）


class MemoryCategory(Enum):
    """记忆类别"""
    USER_PREFERENCE = "user_preference"      # 用户偏好
    RISK_SETTING = "risk_setting"            # 风险设置
    TRADING_DECISION = "trading_decision"    # 交易决策
    SYSTEM_INSTRUCTION = "system_instruction" # 系统指令
    CONVERSATION = "conversation"            # 对话记录
    MARKET_INSIGHT = "market_insight"        # 市场洞察
    LEARNING = "learning"                    # 学习总结
    TRADE_OPEN = "trade_open"                # 开仓记录
    TRADE_CLOSE = "trade_close"              # 平仓记录
    PNL_RECORD = "pnl_record"                # 盈亏记录
    STRATEGY_OPTIMIZATION = "strategy_optimization"  # 策略优化
    RISK_EVENT = "risk_event"                # 风险事件


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    category: MemoryCategory
    priority: MemoryPriority
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "category": self.category.value,
            "priority": self.priority.value,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'MemoryEntry':
        return cls(
            id=data["id"],
            category=MemoryCategory(data["category"]),
            priority=MemoryPriority(data["priority"]),
            content=data["content"],
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None,
            access_count=data.get("access_count", 0),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
        )


class EnhancedMemoryManager:
    """
    增强记忆管理器
    
    参考 OpenClaw 的记忆架构：
    1. 工作区文件作为核心长期记忆
    2. 会话级别的短期记忆
    3. 智能识别和保存重要信息
    4. 自动记忆压缩和摘要
    """
    
    IMPORTANT_PATTERNS = {
        "risk_preference": [
            r"风险偏好[是为：:]\s*(.+)",
            r"我是(.+型).*(?:投资者|交易者)",
            r"(?:保守|稳健|激进)型",
            r"风险承受能力[是为：:]\s*(.+)",
            r"最大亏损[是为：:]\s*(.+)",
        ],
        "trading_preference": [
            r"交易偏好[是为：:]\s*(.+)",
            r"喜欢交易(.+)",
            r"偏好(.+交易)",
            r"主要交易(.+)",
        ],
        "position_preference": [
            r"仓位[是为：:]\s*(.+)",
            r"杠杆[是为：:]\s*(.+)",
            r"止损[是为：:]\s*(.+)",
            r"止盈[是为：:]\s*(.+)",
        ],
        "user_instruction": [
            r"记住[：:]?\s*(.+)",
            r"记得[：:]?\s*(.+)",
            r"以后(.+)",
            r"总是(.+)",
            r"不要(.+)",
            r"必须(.+)",
        ],
        "market_insight": [
            r"发现(.+规律)",
            r"(.+)支撑位",
            r"(.+)阻力位",
            r"趋势[是为：:]\s*(.+)",
        ]
    }
    
    def __init__(self, workspace_path: str = None, storage_path: str = None):
        self.workspace_path = Path(workspace_path) if workspace_path else Path("workspace")
        self.storage_path = Path(storage_path) if storage_path else Path("data/memory")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.workspace_memory: Dict[str, str] = {}
        self.short_term_memory: List[MemoryEntry] = []
        self.long_term_memory: List[MemoryEntry] = []
        
        self.session_id: Optional[str] = None
        self.session_start: Optional[datetime] = None
        self.conversation_history: List[Dict[str, str]] = []
        
        self.config = {
            "short_term_max": 100,
            "short_term_window_hours": 24,
            "long_term_max": 500,
            "conversation_max": 50,
            "auto_save_interval": 60,
            "important_threshold": 0.7,
        }
        
        self.workspace_files = [
            "SOUL.md",
            "IDENTITY.md",
            "USER.md",
            "TRADING.md",
            "INSTRUCTIONS.md",
            "AGENTS.md",
        ]
        
        self._load_workspace_memory()
        self._load_memory()
        
        logger.info("✅ 增强记忆管理器初始化完成")
    
    def _load_workspace_memory(self) -> None:
        """加载工作区记忆文件"""
        for filename in self.workspace_files:
            file_path = self.workspace_path / filename
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        self.workspace_memory[filename] = content
                        logger.info(f"📄 加载工作区文件: {filename}")
                except Exception as e:
                    logger.error(f"加载工作区文件失败 {filename}: {e}")
    
    def _load_memory(self) -> None:
        """加载持久化记忆"""
        memory_file = self.storage_path / "enhanced_memory.json"
        if not memory_file.exists():
            return
        
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for entry_data in data.get("short_term", []):
                self.short_term_memory.append(MemoryEntry.from_dict(entry_data))
            
            for entry_data in data.get("long_term", []):
                self.long_term_memory.append(MemoryEntry.from_dict(entry_data))
            
            logger.info(f"📂 加载记忆: 短期 {len(self.short_term_memory)}, 长期 {len(self.long_term_memory)}")
            
        except Exception as e:
            logger.error(f"加载记忆失败: {e}")
    
    def _save_memory(self) -> None:
        """保存记忆到文件"""
        memory_file = self.storage_path / "enhanced_memory.json"
        
        try:
            data = {
                "short_term": [m.to_dict() for m in self.short_term_memory],
                "long_term": [m.to_dict() for m in self.long_term_memory],
                "session_id": self.session_id,
                "updated_at": datetime.now().isoformat()
            }
            
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")
    
    def start_session(self, session_id: str = None) -> str:
        """开始新会话"""
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.session_start = datetime.now()
        self.conversation_history = []
        
        logger.info(f"🆕 开始新会话: {self.session_id}")
        return self.session_id
    
    def add_message(self, role: str, content: str) -> None:
        """添加对话消息"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        if len(self.conversation_history) > self.config["conversation_max"]:
            self.conversation_history = self.conversation_history[-self.config["conversation_max"]:]
        
        if role == "user":
            self._analyze_and_save_important(content)
        
        self._save_memory()
    
    def _analyze_and_save_important(self, content: str) -> Optional[MemoryEntry]:
        """分析用户输入，识别并保存重要信息"""
        important_info = self._extract_important_info(content)
        
        if important_info:
            category, extracted_content = important_info
            entry = self._create_memory_entry(category, extracted_content, content)
            self.long_term_memory.append(entry)
            self._cleanup_long_term()
            
            logger.info(f"💾 保存重要信息到长期记忆: [{category.value}] {extracted_content[:50]}...")
            
            self._update_workspace_file(category, extracted_content)
            
            return entry
        
        return None
    
    def _extract_important_info(self, content: str) -> Optional[Tuple[MemoryCategory, str]]:
        """提取重要信息"""
        content_lower = content.lower()
        
        for info_type, patterns in self.IMPORTANT_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    extracted = match.group(1) if match.groups() else match.group(0)
                    
                    if info_type == "risk_preference":
                        return MemoryCategory.RISK_SETTING, f"风险偏好: {extracted}"
                    elif info_type == "trading_preference":
                        return MemoryCategory.USER_PREFERENCE, f"交易偏好: {extracted}"
                    elif info_type == "position_preference":
                        return MemoryCategory.USER_PREFERENCE, f"仓位设置: {extracted}"
                    elif info_type == "user_instruction":
                        return MemoryCategory.SYSTEM_INSTRUCTION, f"用户指令: {extracted}"
                    elif info_type == "market_insight":
                        return MemoryCategory.MARKET_INSIGHT, f"市场洞察: {extracted}"
        
        important_keywords = [
            "偏好", "喜欢", "想要", "需要", "必须", "不要", "记住",
            "风险", "止损", "止盈", "仓位", "杠杆", "保守", "激进", "稳健"
        ]
        
        for keyword in important_keywords:
            if keyword in content and len(content) < 200:
                return MemoryCategory.USER_PREFERENCE, content
        
        return None
    
    def _create_memory_entry(self, category: MemoryCategory, content: str, 
                            original_content: str) -> MemoryEntry:
        """创建记忆条目"""
        priority = MemoryPriority.NORMAL
        
        if category in [MemoryCategory.RISK_SETTING, MemoryCategory.SYSTEM_INSTRUCTION]:
            priority = MemoryPriority.CRITICAL
        elif category in [MemoryCategory.USER_PREFERENCE, MemoryCategory.TRADING_DECISION]:
            priority = MemoryPriority.HIGH
        
        return MemoryEntry(
            id=f"mem_{datetime.now().timestamp()}",
            category=category,
            priority=priority,
            content=content,
            metadata={"original": original_content[:500]},
            created_at=datetime.now()
        )
    
    def _update_workspace_file(self, category: MemoryCategory, content: str) -> None:
        """更新工作区文件"""
        if category == MemoryCategory.USER_PREFERENCE or category == MemoryCategory.RISK_SETTING:
            user_file = self.workspace_path / "USER.md"
            
            try:
                existing_content = ""
                if user_file.exists():
                    with open(user_file, "r", encoding="utf-8") as f:
                        existing_content = f.read()
                
                if content not in existing_content:
                    new_section = f"\n\n## 更新于 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{content}\n"
                    
                    with open(user_file, "a", encoding="utf-8") as f:
                        f.write(new_section)
                    
                    self.workspace_memory["USER.md"] = existing_content + new_section
                    logger.info(f"📝 更新工作区文件: USER.md")
                    
            except Exception as e:
                logger.error(f"更新工作区文件失败: {e}")
    
    def _cleanup_long_term(self) -> None:
        """清理长期记忆"""
        if len(self.long_term_memory) > self.config["long_term_max"]:
            sorted_memory = sorted(
                self.long_term_memory,
                key=lambda m: (m.priority.value, m.access_count, m.created_at),
                reverse=True
            )
            self.long_term_memory = sorted_memory[:self.config["long_term_max"]]
    
    def build_memory_context(self, query: str = "") -> str:
        """
        构建记忆上下文，用于注入到AI提示词中
        
        参考 OpenClaw 的做法：在新会话的第一轮，将工作区文件内容直接注入
        """
        context_parts = []
        
        context_parts.append("═══════════════════════════════════════════")
        context_parts.append("📚 【我的长期记忆 - 核心文件】")
        context_parts.append("═══════════════════════════════════════════")
        
        priority_files = ["SOUL.md", "IDENTITY.md", "USER.md", "TRADING.md", "INSTRUCTIONS.md"]
        
        for filename in priority_files:
            if filename in self.workspace_memory:
                context_parts.append(f"\n【{filename}】")
                content = self.workspace_memory[filename]
                if len(content) > 2000:
                    content = content[:2000] + "\n... (内容过长已截断)"
                context_parts.append(content)
        
        context_parts.append("\n═══════════════════════════════════════════")
        
        if self.long_term_memory:
            context_parts.append("\n📋 【重要记忆记录】:")
            
            critical_memories = [m for m in self.long_term_memory 
                               if m.priority == MemoryPriority.CRITICAL]
            for mem in critical_memories[-10:]:
                context_parts.append(f"  ⭐ [{mem.category.value}] {mem.content}")
            
            high_memories = [m for m in self.long_term_memory 
                           if m.priority == MemoryPriority.HIGH]
            for mem in high_memories[-5:]:
                context_parts.append(f"  📌 [{mem.category.value}] {mem.content}")
        
        trading_context = self.build_trading_memory_context()
        context_parts.append("\n" + trading_context)
        
        if self.conversation_history:
            context_parts.append("\n💬 【最近对话】:")
            for msg in self.conversation_history[-5:]:
                role = "用户" if msg["role"] == "user" else "AI"
                content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
                context_parts.append(f"  {role}: {content}")
        
        context_parts.append("\n═══════════════════════════════════════════")
        
        return "\n".join(context_parts)
    
    def get_relevant_memories(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """获取相关记忆"""
        query_lower = query.lower()
        scored_memories = []
        
        for mem in self.long_term_memory:
            score = 0
            
            if query_lower in mem.content.lower():
                score += 10
            
            for word in query_lower.split():
                if word in mem.content.lower():
                    score += 2
            
            score += mem.priority.value * -2
            score += mem.access_count * 0.5
            
            if score > 0:
                scored_memories.append((score, mem))
        
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        result = [m for _, m in scored_memories[:limit]]
        
        for mem in result:
            mem.access_count += 1
            mem.last_accessed = datetime.now()
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        return {
            "short_term_count": len(self.short_term_memory),
            "long_term_count": len(self.long_term_memory),
            "workspace_files": list(self.workspace_memory.keys()),
            "conversation_count": len(self.conversation_history),
            "session_id": self.session_id,
            "session_start": self.session_start.isoformat() if self.session_start else None,
            "categories": {
                cat.value: sum(1 for m in self.long_term_memory if m.category == cat)
                for cat in MemoryCategory
            }
        }
    
    def force_save_user_preference(self, key: str, value: str) -> None:
        """强制保存用户偏好"""
        entry = MemoryEntry(
            id=f"pref_{datetime.now().timestamp()}",
            category=MemoryCategory.USER_PREFERENCE,
            priority=MemoryPriority.CRITICAL,
            content=f"{key}: {value}",
            metadata={"key": key, "value": value},
            created_at=datetime.now()
        )
        
        self.long_term_memory.append(entry)
        self._update_workspace_file(MemoryCategory.USER_PREFERENCE, f"{key}: {value}")
        self._save_memory()
        
        logger.info(f"💾 强制保存用户偏好: {key} = {value}")
    
    def update_workspace_file_content(self, filename: str, content: str) -> bool:
        """直接更新工作区文件内容"""
        if filename not in self.workspace_files:
            logger.warning(f"未知的工作区文件: {filename}")
            return False
        
        try:
            file_path = self.workspace_path / filename
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            self.workspace_memory[filename] = content
            logger.info(f"📝 更新工作区文件: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"更新工作区文件失败: {e}")
            return False
    
    def save_trade_open(self, symbol: str, side: str, price: float, 
                       quantity: float, reason: str = "", 
                       stop_loss: float = None, take_profit: float = None,
                       strategy: str = "") -> MemoryEntry:
        """
        保存开仓记录
        
        Args:
            symbol: 交易对
            side: 方向 (long/short)
            price: 开仓价格
            quantity: 数量
            reason: 开仓原因
            stop_loss: 止损价格
            take_profit: 止盈价格
            strategy: 使用的策略
            
        Returns:
            记忆条目
        """
        side_text = "开多" if side == "long" else "开空"
        content = f"{side_text} {symbol} @ {price}, 数量: {quantity}"
        if reason:
            content += f", 原因: {reason}"
        if strategy:
            content += f", 策略: {strategy}"
        
        metadata = {
            "symbol": symbol,
            "side": side,
            "price": price,
            "quantity": quantity,
            "reason": reason,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "strategy": strategy,
            "timestamp": datetime.now().isoformat()
        }
        
        entry = MemoryEntry(
            id=f"trade_open_{datetime.now().timestamp()}",
            category=MemoryCategory.TRADE_OPEN,
            priority=MemoryPriority.HIGH,
            content=content,
            metadata=metadata,
            created_at=datetime.now()
        )
        
        self.long_term_memory.append(entry)
        self._save_memory()
        
        logger.info(f"📊 保存开仓记录: {content}")
        
        self._update_trading_file(entry)
        
        return entry
    
    def save_trade_close(self, symbol: str, side: str, open_price: float,
                        close_price: float, quantity: float, pnl: float,
                        pnl_percent: float, reason: str = "",
                        hold_duration: str = "") -> MemoryEntry:
        """
        保存平仓记录
        
        Args:
            symbol: 交易对
            side: 方向 (long/short)
            open_price: 开仓价格
            close_price: 平仓价格
            quantity: 数量
            pnl: 盈亏金额
            pnl_percent: 盈亏百分比
            reason: 平仓原因
            hold_duration: 持仓时长
            
        Returns:
            记忆条目
        """
        side_text = "平多" if side == "long" else "平空"
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        content = f"{side_text} {symbol} @ {close_price}, 盈亏: {pnl:+.2f} USDT ({pnl_percent:+.2f}%) {pnl_emoji}"
        if reason:
            content += f", 原因: {reason}"
        
        metadata = {
            "symbol": symbol,
            "side": side,
            "open_price": open_price,
            "close_price": close_price,
            "quantity": quantity,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "reason": reason,
            "hold_duration": hold_duration,
            "is_profit": pnl >= 0,
            "timestamp": datetime.now().isoformat()
        }
        
        priority = MemoryPriority.HIGH
        if abs(pnl_percent) > 5:
            priority = MemoryPriority.CRITICAL
        
        entry = MemoryEntry(
            id=f"trade_close_{datetime.now().timestamp()}",
            category=MemoryCategory.TRADE_CLOSE,
            priority=priority,
            content=content,
            metadata=metadata,
            created_at=datetime.now()
        )
        
        self.long_term_memory.append(entry)
        self._save_memory()
        
        logger.info(f"💰 保存平仓记录: {content}")
        
        self._update_trading_file(entry)
        
        self._update_pnl_summary()
        
        return entry
    
    def save_pnl_record(self, period: str, total_pnl: float, 
                       trade_count: int, win_count: int, lose_count: int,
                       win_rate: float, best_trade: Dict = None,
                       worst_trade: Dict = None) -> MemoryEntry:
        """
        保存盈亏统计记录
        
        Args:
            period: 统计周期 (daily/weekly/monthly)
            total_pnl: 总盈亏
            trade_count: 交易次数
            win_count: 盈利次数
            lose_count: 亏损次数
            win_rate: 胜率
            best_trade: 最佳交易
            worst_trade: 最差交易
            
        Returns:
            记忆条目
        """
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        content = f"[{period}] 总盈亏: {total_pnl:+.2f} USDT {pnl_emoji}, 交易: {trade_count}笔, 胜率: {win_rate:.1%}"
        
        metadata = {
            "period": period,
            "total_pnl": total_pnl,
            "trade_count": trade_count,
            "win_count": win_count,
            "lose_count": lose_count,
            "win_rate": win_rate,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "timestamp": datetime.now().isoformat()
        }
        
        priority = MemoryPriority.HIGH if total_pnl >= 0 else MemoryPriority.CRITICAL
        
        entry = MemoryEntry(
            id=f"pnl_{period}_{datetime.now().strftime('%Y%m%d')}",
            category=MemoryCategory.PNL_RECORD,
            priority=priority,
            content=content,
            metadata=metadata,
            created_at=datetime.now()
        )
        
        self.long_term_memory.append(entry)
        self._cleanup_long_term()
        self._save_memory()
        
        logger.info(f"📊 保存盈亏统计: {content}")
        
        return entry
    
    def save_strategy_optimization(self, strategy_name: str, 
                                  optimization_type: str,
                                  old_params: Dict, new_params: Dict,
                                  reason: str, expected_improvement: str = "") -> MemoryEntry:
        """
        保存策略优化记录
        
        Args:
            strategy_name: 策略名称
            optimization_type: 优化类型 (parameter/rule/logic)
            old_params: 旧参数
            new_params: 新参数
            reason: 优化原因
            expected_improvement: 预期改进
            
        Returns:
            记忆条目
        """
        content = f"策略优化 [{strategy_name}]: {optimization_type}"
        if reason:
            content += f", 原因: {reason}"
        if expected_improvement:
            content += f", 预期: {expected_improvement}"
        
        metadata = {
            "strategy_name": strategy_name,
            "optimization_type": optimization_type,
            "old_params": old_params,
            "new_params": new_params,
            "reason": reason,
            "expected_improvement": expected_improvement,
            "timestamp": datetime.now().isoformat()
        }
        
        entry = MemoryEntry(
            id=f"strategy_opt_{datetime.now().timestamp()}",
            category=MemoryCategory.STRATEGY_OPTIMIZATION,
            priority=MemoryPriority.HIGH,
            content=content,
            metadata=metadata,
            created_at=datetime.now()
        )
        
        self.long_term_memory.append(entry)
        self._save_memory()
        
        logger.info(f"🔧 保存策略优化记录: {content}")
        
        self._update_trading_file(entry)
        
        return entry
    
    def save_risk_event(self, event_type: str, symbol: str, 
                       description: str, action_taken: str,
                       impact: str = "") -> MemoryEntry:
        """
        保存风险事件记录
        
        Args:
            event_type: 事件类型 (liquidation_warning/margin_call/stop_loss/etc)
            symbol: 相关交易对
            description: 事件描述
            action_taken: 采取的行动
            impact: 影响
            
        Returns:
            记忆条目
        """
        content = f"⚠️ 风险事件 [{event_type}] {symbol}: {description}"
        if action_taken:
            content += f", 处理: {action_taken}"
        
        metadata = {
            "event_type": event_type,
            "symbol": symbol,
            "description": description,
            "action_taken": action_taken,
            "impact": impact,
            "timestamp": datetime.now().isoformat()
        }
        
        entry = MemoryEntry(
            id=f"risk_{datetime.now().timestamp()}",
            category=MemoryCategory.RISK_EVENT,
            priority=MemoryPriority.CRITICAL,
            content=content,
            metadata=metadata,
            created_at=datetime.now()
        )
        
        self.long_term_memory.append(entry)
        self._save_memory()
        
        logger.warning(f"⚠️ 保存风险事件记录: {content}")
        
        return entry
    
    def _update_trading_file(self, entry: MemoryEntry) -> None:
        """更新交易记录文件"""
        trading_file = self.workspace_path / "TRADING.md"
        
        try:
            existing_content = ""
            if trading_file.exists():
                with open(trading_file, "r", encoding="utf-8") as f:
                    existing_content = f.read()
            
            date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            if "## 交易记录" not in existing_content:
                new_section = f"\n\n## 交易记录\n\n### {datetime.now().strftime('%Y-%m-%d')}\n\n"
            elif f"### {datetime.now().strftime('%Y-%m-%d')}" not in existing_content:
                new_section = f"\n\n### {datetime.now().strftime('%Y-%m-%d')}\n\n"
            else:
                new_section = ""
            
            record_line = f"- [{date_str}] [{entry.category.value}] {entry.content}\n"
            
            if record_line not in existing_content:
                with open(trading_file, "a", encoding="utf-8") as f:
                    f.write(new_section + record_line)
                
                self.workspace_memory["TRADING.md"] = existing_content + new_section + record_line
                logger.info(f"📝 更新交易记录文件")
                
        except Exception as e:
            logger.error(f"更新交易记录文件失败: {e}")
    
    def _update_pnl_summary(self) -> None:
        """更新盈亏摘要"""
        try:
            close_trades = [m for m in self.long_term_memory 
                          if m.category == MemoryCategory.TRADE_CLOSE]
            
            if not close_trades:
                return
            
            recent_trades = close_trades[-20:]
            
            total_pnl = sum(m.metadata.get("pnl", 0) for m in recent_trades)
            win_count = sum(1 for m in recent_trades if m.metadata.get("is_profit", False))
            lose_count = len(recent_trades) - win_count
            win_rate = win_count / len(recent_trades) if recent_trades else 0
            
            best_trade = max(recent_trades, key=lambda m: m.metadata.get("pnl", 0))
            worst_trade = min(recent_trades, key=lambda m: m.metadata.get("pnl", 0))
            
            summary = f"""
## 盈亏摘要 (最近{len(recent_trades)}笔交易)

- **总盈亏**: {total_pnl:+.2f} USDT
- **胜率**: {win_rate:.1%} ({win_count}胜/{lose_count}负)
- **最佳交易**: {best_trade.content}
- **最差交易**: {worst_trade.content}
- **更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
            
            trading_file = self.workspace_path / "TRADING.md"
            if trading_file.exists():
                with open(trading_file, "r", encoding="utf-8") as f:
                    content = f.read()
                
                if "## 盈亏摘要" in content:
                    import re
                    content = re.sub(
                        r'## 盈亏摘要.*?(?=##|$)',
                        summary + "\n",
                        content,
                        flags=re.DOTALL
                    )
                else:
                    content += "\n" + summary
                
                with open(trading_file, "w", encoding="utf-8") as f:
                    f.write(content)
                
                self.workspace_memory["TRADING.md"] = content
                
        except Exception as e:
            logger.error(f"更新盈亏摘要失败: {e}")
    
    def get_trade_statistics(self, days: int = 30) -> Dict[str, Any]:
        """获取交易统计"""
        cutoff = datetime.now() - timedelta(days=days)
        
        recent_trades = [
            m for m in self.long_term_memory
            if m.category in [MemoryCategory.TRADE_OPEN, MemoryCategory.TRADE_CLOSE]
            and m.created_at >= cutoff
        ]
        
        close_trades = [m for m in recent_trades if m.category == MemoryCategory.TRADE_CLOSE]
        
        if not close_trades:
            return {
                "period_days": days,
                "total_trades": 0,
                "total_pnl": 0,
                "win_rate": 0,
                "avg_pnl": 0
            }
        
        total_pnl = sum(m.metadata.get("pnl", 0) for m in close_trades)
        win_count = sum(1 for m in close_trades if m.metadata.get("is_profit", False))
        
        return {
            "period_days": days,
            "total_trades": len(close_trades),
            "total_pnl": total_pnl,
            "win_rate": win_count / len(close_trades),
            "win_count": win_count,
            "lose_count": len(close_trades) - win_count,
            "avg_pnl": total_pnl / len(close_trades),
            "best_trade": max(close_trades, key=lambda m: m.metadata.get("pnl", 0)).content if close_trades else None,
            "worst_trade": min(close_trades, key=lambda m: m.metadata.get("pnl", 0)).content if close_trades else None
        }
    
    def get_strategy_history(self) -> List[Dict[str, Any]]:
        """获取策略优化历史"""
        optimizations = [
            m for m in self.long_term_memory
            if m.category == MemoryCategory.STRATEGY_OPTIMIZATION
        ]
        
        return [
            {
                "timestamp": m.created_at.isoformat(),
                "strategy": m.metadata.get("strategy_name"),
                "type": m.metadata.get("optimization_type"),
                "reason": m.metadata.get("reason"),
                "content": m.content
            }
            for m in sorted(optimizations, key=lambda x: x.created_at, reverse=True)
        ]
    
    def build_trading_memory_context(self) -> str:
        """构建交易记忆上下文"""
        context_parts = []
        
        context_parts.append("═══════════════════════════════════════════")
        context_parts.append("📊 【交易记忆】")
        context_parts.append("═══════════════════════════════════════════")
        
        stats = self.get_trade_statistics(30)
        if stats["total_trades"] > 0:
            context_parts.append(f"\n📈 近30天统计:")
            context_parts.append(f"  - 交易次数: {stats['total_trades']}笔")
            context_parts.append(f"  - 总盈亏: {stats['total_pnl']:+.2f} USDT")
            context_parts.append(f"  - 胜率: {stats['win_rate']:.1%}")
            if stats.get("best_trade"):
                context_parts.append(f"  - 最佳交易: {stats['best_trade']}")
        
        close_trades = [m for m in self.long_term_memory 
                       if m.category == MemoryCategory.TRADE_CLOSE][-5:]
        if close_trades:
            context_parts.append(f"\n💰 最近平仓记录:")
            for trade in close_trades:
                context_parts.append(f"  - {trade.content}")
        
        optimizations = [m for m in self.long_term_memory 
                        if m.category == MemoryCategory.STRATEGY_OPTIMIZATION][-3:]
        if optimizations:
            context_parts.append(f"\n🔧 最近策略优化:")
            for opt in optimizations:
                context_parts.append(f"  - {opt.content}")
        
        risk_events = [m for m in self.long_term_memory 
                      if m.category == MemoryCategory.RISK_EVENT][-3:]
        if risk_events:
            context_parts.append(f"\n⚠️ 最近风险事件:")
            for event in risk_events:
                context_parts.append(f"  - {event.content}")
        
        context_parts.append("\n═══════════════════════════════════════════")
        
        return "\n".join(context_parts)


_enhanced_memory_instance: Optional[EnhancedMemoryManager] = None


def get_enhanced_memory_manager(workspace_path: str = None, 
                                storage_path: str = None) -> EnhancedMemoryManager:
    """获取增强记忆管理器单例"""
    global _enhanced_memory_instance
    
    if _enhanced_memory_instance is None:
        _enhanced_memory_instance = EnhancedMemoryManager(workspace_path, storage_path)
    
    return _enhanced_memory_instance
