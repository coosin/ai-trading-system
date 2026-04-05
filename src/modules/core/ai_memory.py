"""
AI记忆管理系统 - 让AI拥有记忆

核心功能：
1. 短期记忆 - 对话上下文
2. 长期记忆 - 用户偏好、历史交易、系统指令
3. 记忆检索和注入
4. 记忆总结和更新
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """记忆类型"""
    SHORT_TERM = "short_term"    # 短期记忆（对话上下文）
    LONG_TERM = "long_term"      # 长期记忆
    TRADE_HISTORY = "trade_history" # 交易历史
    USER_PREF = "user_preference"  # 用户偏好
    SYSTEM_INSTRUCTION = "system_instruction" # 系统指令


@dataclass
class MemoryItem:
    """记忆条目"""
    memory_id: str
    memory_type: MemoryType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5  # 重要性 0-1
    timestamp: datetime = field(default_factory=datetime.now)
    accessed_count: int = 0
    last_accessed: Optional[datetime] = None


class AIMemoryManager:
    """
    AI记忆管理器
    
    让AI拥有：
    1. 对话上下文记忆
    2. 历史交易记忆和总结
    3. 用户偏好和工作指令记忆
    4. 记忆检索和总结
    5. 文件化长期记忆（SOUL.md, IDENTITY.md, USER.md等）
    """
    
    def __init__(self, storage_path: Optional[str] = None, workspace_path: Optional[str] = None):
        """
        初始化AI记忆管理器
        
        Args:
            storage_path: 记忆存储路径
            workspace_path: 工作区路径（包含记忆文件）
        """
        self.storage_path = Path(storage_path) if storage_path else Path("data/memory")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 工作区路径（包含SOUL.md, IDENTITY.md等文件）
        self.workspace_path = Path(workspace_path) if workspace_path else Path("workspace")
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        
        # 内存中的记忆存储
        self.short_term_memory: List[MemoryItem] = []
        self.long_term_memory: List[MemoryItem] = []
        
        # 记忆索引
        self.memory_index: Dict[str, MemoryItem] = {}
        
        # 文件化记忆缓存
        self.workspace_memory: Dict[str, str] = {}
        
        # 配置
        self.config = {
            "short_term_max": 50,        # 短期记忆最大数量
            "short_term_window": 3600,   # 短期记忆时间窗口（秒）
            "long_term_max": 1000,       # 长期记忆最大数量
            "retrieval_top_k": 5,         # 检索返回数量
            "memory_decay_rate": 0.01,    # 记忆衰减率
        }
        
        # 需要加载的工作区记忆文件
        self.memory_files = [
            "SOUL.md",
            "IDENTITY.md", 
            "USER.md",
            "TRADING.md",
            "INSTRUCTIONS.md"
        ]
        
        # 加载持久化记忆
        self._load_memory()
        
        # 加载工作区文件化记忆
        self._load_workspace_memory()
        
        logger.info("✅ AI记忆管理器初始化完成")
    
    async def initialize(self) -> bool:
        """异步初始化（兼容接口）"""
        return True
    
    async def add_short_term_memory(self, content: str, 
                                    metadata: Dict[str, Any] = None,
                                    importance: float = 0.5) -> str:
        """
        添加短期记忆（对话上下文）
        
        Args:
            content: 记忆内容
            metadata: 元数据
            importance: 重要性 0-1
            
        Returns:
            记忆ID
        """
        if self._is_garbage_content(content):
            logger.debug(f"🚫 过滤垃圾记忆: {content[:50]}...")
            return None
        
        memory_id = f"st_{datetime.now().timestamp()}"
        
        item = MemoryItem(
            memory_id=memory_id,
            memory_type=MemoryType.SHORT_TERM,
            content=content,
            metadata=metadata or {},
            importance=importance,
            timestamp=datetime.now()
        )
        
        self.short_term_memory.append(item)
        self.memory_index[memory_id] = item
        
        self._cleanup_short_term()
        
        self._save_memory()
        
        logger.debug(f"📝 添加短期记忆: {content[:50]}...")
        return memory_id
    
    def _is_garbage_content(self, content: str) -> bool:
        """判断是否为垃圾内容（不应保存的记忆）"""
        garbage_patterns = [
            "分析以下市场数据",
            "请提供：",
            "市场趋势分析",
            "关键支撑位和阻力位",
            "技术指标解读",
            "市场情绪分析",
            "请以JSON格式返回",
            "MarketData(symbol=",
            "'symbol': '",
            "'price': ",
            "'trend': '",
            "'sentiment': '",
        ]
        
        garbage_count = sum(1 for pattern in garbage_patterns if pattern in content)
        
        if garbage_count >= 3:
            return True
        
        if "分析以下市场数据" in content and len(content) > 200:
            return True
        
        return False
    
    async def add_long_term_memory(self, content: str, 
                                   memory_type: MemoryType = MemoryType.LONG_TERM,
                                   metadata: Dict[str, Any] = None,
                                   importance: float = 0.7) -> str:
        """
        添加长期记忆
        
        Args:
            content: 记忆内容
            memory_type: 记忆类型
            metadata: 元数据
            importance: 重要性 0-1
            
        Returns:
            记忆ID
        """
        memory_id = f"lt_{datetime.now().timestamp()}"
        
        item = MemoryItem(
            memory_id=memory_id,
            memory_type=memory_type,
            content=content,
            metadata=metadata or {},
            importance=importance,
            timestamp=datetime.now()
        )
        
        self.long_term_memory.append(item)
        self.memory_index[memory_id] = item
        
        # 清理长期记忆
        self._cleanup_long_term()
        
        # 持久化
        self._save_memory()
        
        logger.info(f"💾 添加长期记忆 [{memory_type.value}]: {content[:80]}...")
        return memory_id
    
    async def add_trade_memory(self, trade: Dict[str, Any], 
                              summary: Optional[str] = None) -> str:
        """
        添加交易记忆
        
        Args:
            trade: 交易数据
            summary: 交易总结（可选）
            
        Returns:
            记忆ID
        """
        content = summary or self._generate_trade_summary(trade)
        
        metadata = {
            "trade": trade,
            "symbol": trade.get("symbol"),
            "action": trade.get("action"),
            "profit": trade.get("pnl", 0),
            "profit_percent": trade.get("pnl_percent", 0)
        }
        
        # 根据盈亏设置重要性
        profit = trade.get("pnl", 0)
        importance = 0.6
        if profit > 0:
            importance = min(0.9, 0.7 + abs(profit) / 1000)
        elif profit < 0:
            importance = min(0.95, 0.8 + abs(profit) / 500)  # 亏损更重要
        
        return await self.add_long_term_memory(
            content=content,
            memory_type=MemoryType.TRADE_HISTORY,
            metadata=metadata,
            importance=importance
        )
    
    async def add_user_preference(self, key: str, value: Any, 
                                  description: Optional[str] = None) -> str:
        """
        添加用户偏好
        
        Args:
            key: 偏好键
            value: 偏好值
            description: 描述
            
        Returns:
            记忆ID
        """
        content = f"用户偏好: {key} = {value}"
        if description:
            content += f" ({description})"
        
        metadata = {
            "key": key,
            "value": value,
            "description": description
        }
        
        return await self.add_long_term_memory(
            content=content,
            memory_type=MemoryType.USER_PREF,
            metadata=metadata,
            importance=0.8
        )
    
    async def add_system_instruction(self, instruction: str, 
                                    context: Optional[str] = None) -> str:
        """
        添加系统指令（工作要求、任务等）
        
        Args:
            instruction: 指令内容
            context: 上下文
            
        Returns:
            记忆ID
        """
        content = f"系统指令: {instruction}"
        if context:
            content += f"\n上下文: {context}"
        
        metadata = {
            "instruction": instruction,
            "context": context
        }
        
        return await self.add_long_term_memory(
            content=content,
            memory_type=MemoryType.SYSTEM_INSTRUCTION,
            metadata=metadata,
            importance=0.9
        )
    
    async def retrieve_memory(self, query: str, 
                             memory_types: Optional[List[MemoryType]] = None,
                             top_k: Optional[int] = None) -> List[MemoryItem]:
        """
        检索相关记忆
        
        Args:
            query: 查询关键词
            memory_types: 记忆类型过滤
            top_k: 返回数量
            
        Returns:
            相关记忆列表
        """
        top_k = top_k or self.config["retrieval_top_k"]
        
        # 选择记忆池
        memories = []
        if memory_types:
            for mem_type in memory_types:
                if mem_type == MemoryType.SHORT_TERM:
                    memories.extend(self.short_term_memory)
                else:
                    memories.extend([m for m in self.long_term_memory if m.memory_type == mem_type])
        else:
            memories = self.short_term_memory + self.long_term_memory
        
        # 简单的关键词匹配检索
        query_words = set(query.lower().split())
        scored_memories = []
        
        for item in memories:
            score = 0.0
            
            # 内容匹配
            content_lower = item.content.lower()
            for word in query_words:
                if word in content_lower:
                    score += 0.3
            
            # 时间衰减
            time_diff = (datetime.now() - item.timestamp).total_seconds()
            time_decay = max(0.1, 1.0 - time_diff * self.config["memory_decay_rate"] / 86400)
            score *= time_decay
            
            # 重要性权重
            score *= item.importance
            
            # 访问次数（重要记忆被访问更多）
            score *= (1.0 + item.accessed_count * 0.05)
            
            if score > 0:
                scored_memories.append((score, item))
        
        # 排序并返回top_k
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        result = [item for _, item in scored_memories[:top_k]]
        
        # 更新访问次数
        for item in result:
            item.accessed_count += 1
            item.last_accessed = datetime.now()
        
        if result:
            logger.debug(f"🔍 检索到 {len(result)} 条相关记忆")
        
        return result
    
    async def summarize_trade_history(self, days: int = 30) -> str:
        """
        总结交易历史
        
        Args:
            days: 天数
            
        Returns:
            交易总结
        """
        cutoff = datetime.now() - timedelta(days=days)
        recent_trades = [m for m in self.long_term_memory 
                        if m.memory_type == MemoryType.TRADE_HISTORY 
                        and m.timestamp >= cutoff]
        
        return self._summarize_trades(recent_trades)
    
    def _summarize_trades(self, trades: List[MemoryItem]) -> str:
        """总结交易列表"""
        if not trades:
            return "暂无交易记录"
        
        total_profit = 0.0
        win_count = 0
        lose_count = 0
        symbols = set()
        
        for trade in trades:
            trade_data = trade.metadata.get("trade", {})
            profit = trade_data.get("pnl", 0)
            total_profit += profit
            
            if profit > 0:
                win_count += 1
            elif profit < 0:
                lose_count += 1
            
            symbol = trade_data.get("symbol")
            if symbol:
                symbols.add(symbol)
        
        total_trades = win_count + lose_count
        win_rate = win_count / total_trades if total_trades > 0 else 0
        
        return (f"总交易: {total_trades}, "
                f"盈利: {win_count}, 亏损: {lose_count}, "
                f"胜率: {win_rate:.1%}, "
                f"总盈亏: {total_profit:+.2f} USDT, "
                f"交易对: {', '.join(symbols) if symbols else 'N/A'}")
    
    def _generate_trade_summary(self, trade: Dict[str, Any]) -> str:
        """生成交易总结"""
        symbol = trade.get("symbol", "N/A")
        action = trade.get("action", "N/A")
        price = trade.get("price", 0)
        quantity = trade.get("quantity", 0)
        pnl = trade.get("pnl", 0)
        pnl_percent = trade.get("pnl_percent", 0)
        reason = trade.get("reason", "")
        
        if action in ["open_long", "open_short"]:
            side = "开多" if "long" in action else "开空"
            return f"{side} {symbol} @ {price}, 数量: {quantity}, 原因: {reason}"
        elif action in ["close_long", "close_short"]:
            side = "平多" if "long" in action else "平空"
            return f"{side} {symbol} @ {price}, 盈亏: {pnl:+.2f} ({pnl_percent:+.2%}), 原因: {reason}"
        else:
            return f"{action} {symbol} @ {price}"
    
    def _cleanup_short_term(self) -> None:
        """清理短期记忆"""
        cutoff = datetime.now() - timedelta(seconds=self.config["short_term_window"])
        
        # 移除过期的
        self.short_term_memory = [
            m for m in self.short_term_memory 
            if m.timestamp >= cutoff
        ]
        
        # 限制数量
        if len(self.short_term_memory) > self.config["short_term_max"]:
            self.short_term_memory = self.short_term_memory[-self.config["short_term_max"]:]
    
    def _cleanup_long_term(self) -> None:
        """清理长期记忆"""
        if len(self.long_term_memory) > self.config["long_term_max"]:
            # 按重要性和访问次数排序，保留最重要的
            sorted_memories = sorted(
                self.long_term_memory,
                key=lambda m: (m.importance, m.accessed_count, m.timestamp),
                reverse=True
            )
            self.long_term_memory = sorted_memories[:self.config["long_term_max"]]
            
            # 更新索引
            self.memory_index = {m.memory_id: m for m in 
                                self.short_term_memory + self.long_term_memory}
    
    def _save_memory(self) -> None:
        """持久化记忆到文件"""
        try:
            memory_data = {
                "short_term": [
                    {
                        "memory_id": m.memory_id,
                        "memory_type": m.memory_type.value,
                        "content": m.content,
                        "metadata": m.metadata,
                        "importance": m.importance,
                        "timestamp": m.timestamp.isoformat(),
                        "accessed_count": m.accessed_count,
                        "last_accessed": m.last_accessed.isoformat() if m.last_accessed else None
                    }
                    for m in self.short_term_memory
                ],
                "long_term": [
                    {
                        "memory_id": m.memory_id,
                        "memory_type": m.memory_type.value,
                        "content": m.content,
                        "metadata": m.metadata,
                        "importance": m.importance,
                        "timestamp": m.timestamp.isoformat(),
                        "accessed_count": m.accessed_count,
                        "last_accessed": m.last_accessed.isoformat() if m.last_accessed else None
                    }
                    for m in self.long_term_memory
                ]
            }
            
            file_path = self.storage_path / "ai_memory.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")
    
    def _load_memory(self) -> None:
        """从文件加载记忆"""
        try:
            file_path = self.storage_path / "ai_memory.json"
            if not file_path.exists():
                return
            
            with open(file_path, "r", encoding="utf-8") as f:
                memory_data = json.load(f)
            
            # 加载短期记忆
            for item_data in memory_data.get("short_term", []):
                item = MemoryItem(
                    memory_id=item_data["memory_id"],
                    memory_type=MemoryType(item_data["memory_type"]),
                    content=item_data["content"],
                    metadata=item_data.get("metadata", {}),
                    importance=item_data.get("importance", 0.5),
                    timestamp=datetime.fromisoformat(item_data["timestamp"]),
                    accessed_count=item_data.get("accessed_count", 0),
                    last_accessed=datetime.fromisoformat(item_data["last_accessed"]) 
                    if item_data.get("last_accessed") else None
                )
                self.short_term_memory.append(item)
                self.memory_index[item.memory_id] = item
            
            # 加载长期记忆
            for item_data in memory_data.get("long_term", []):
                item = MemoryItem(
                    memory_id=item_data["memory_id"],
                    memory_type=MemoryType(item_data["memory_type"]),
                    content=item_data["content"],
                    metadata=item_data.get("metadata", {}),
                    importance=item_data.get("importance", 0.5),
                    timestamp=datetime.fromisoformat(item_data["timestamp"]),
                    accessed_count=item_data.get("accessed_count", 0),
                    last_accessed=datetime.fromisoformat(item_data["last_accessed"]) 
                    if item_data.get("last_accessed") else None
                )
                self.long_term_memory.append(item)
                self.memory_index[item.memory_id] = item
            
            logger.info(f"📂 加载记忆: 短期 {len(self.short_term_memory)}, 长期 {len(self.long_term_memory)}")
            
        except Exception as e:
            logger.error(f"加载记忆失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        return {
            "short_term_count": len(self.short_term_memory),
            "long_term_count": len(self.long_term_memory),
            "trade_count": sum(1 for m in self.long_term_memory 
                             if m.memory_type == MemoryType.TRADE_HISTORY),
            "user_pref_count": sum(1 for m in self.long_term_memory 
                                  if m.memory_type == MemoryType.USER_PREF),
            "system_instruction_count": sum(1 for m in self.long_term_memory 
                                           if m.memory_type == MemoryType.SYSTEM_INSTRUCTION),
            "workspace_memory_files": list(self.workspace_memory.keys()),
            "storage_path": str(self.storage_path),
            "workspace_path": str(self.workspace_path)
        }
    
    def _load_workspace_memory(self) -> None:
        """加载工作区中的记忆文件"""
        for filename in self.memory_files:
            file_path = self.workspace_path / filename
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        self.workspace_memory[filename] = content
                        logger.info(f"📄 加载记忆文件: {filename} ({len(content)} 字符)")
                except Exception as e:
                    logger.error(f"加载记忆文件 {filename} 失败: {e}")
    
    def get_workspace_memory(self, filename: Optional[str] = None) -> Dict[str, str]:
        """
        获取工作区记忆
        
        Args:
            filename: 指定文件名，None则返回所有
            
        Returns:
            记忆内容字典
        """
        if filename:
            return {filename: self.workspace_memory.get(filename, "")}
        return self.workspace_memory.copy()
    
    async def update_workspace_memory(self, filename: str, content: str, 
                                      notify_user: bool = True) -> bool:
        """
        更新工作区记忆文件
        
        Args:
            filename: 文件名
            content: 新内容
            notify_user: 是否通知用户
            
        Returns:
            是否成功
        """
        if filename not in self.memory_files:
            logger.warning(f"尝试更新未注册的记忆文件: {filename}")
            return False
        
        try:
            file_path = self.workspace_path / filename
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            self.workspace_memory[filename] = content
            logger.info(f"✏️ 更新记忆文件: {filename}")
            
            if notify_user:
                await self.add_short_term_memory(
                    f"已更新记忆文件 {filename}，我的长期记忆已改变",
                    importance=0.7
                )
            
            return True
        except Exception as e:
            logger.error(f"更新记忆文件 {filename} 失败: {e}")
            return False
    
    async def build_memory_context(self, query: str = "") -> str:
        """
        构建记忆上下文，用于注入到AI提示词中
        
        Args:
            query: 查询关键词
            
        Returns:
            记忆上下文字符串
        """
        context_parts = []
        
        if self.workspace_memory:
            if "SOUL.md" in self.workspace_memory:
                soul_content = self.workspace_memory["SOUL.md"][:800]
                context_parts.append(f"[核心信念]\n{soul_content}")
            
            if "IDENTITY.md" in self.workspace_memory:
                identity_content = self.workspace_memory["IDENTITY.md"][:600]
                context_parts.append(f"[身份定义]\n{identity_content}")
            
            if "USER.md" in self.workspace_memory:
                user_content = self.workspace_memory["USER.md"][:400]
                context_parts.append(f"[用户信息]\n{user_content}")
            
            if "INSTRUCTIONS.md" in self.workspace_memory:
                inst_content = self.workspace_memory["INSTRUCTIONS.md"][:300]
                context_parts.append(f"[工作指令]\n{inst_content}")
        
        user_prefs = [m for m in self.long_term_memory 
                     if m.memory_type == MemoryType.USER_PREF]
        if user_prefs:
            for pref in user_prefs[-3:]:
                context_parts.append(pref.content[:100])
        
        if self.short_term_memory:
            for item in self.short_term_memory[-3:]:
                context_parts.append(item.content[:100])
        
        if query:
            relevant = await self.retrieve_memory(query, top_k=2)
            if relevant:
                for item in relevant:
                    context_parts.append(item.content[:100])
        
        if context_parts:
            return "\n\n".join(context_parts)
        return ""


    async def cleanup(self):
        """清理资源"""
        pass
