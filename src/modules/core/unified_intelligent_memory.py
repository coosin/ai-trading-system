"""
统一智能记忆系统
整合所有记忆功能，与AI模块深度集成

核心功能：
1. 统一记忆接口 - 整合三个记忆管理器
2. AI预测记忆 - 存储深度学习/强化学习预测结果
3. 市场数据记忆 - 存储第三方数据源数据
4. 模型记忆 - 存储模型训练和更新记录
5. 智能记忆清理 - 自动清理垃圾记忆
6. 语义检索 - 基于重要性的智能检索
"""
import asyncio
import json
import logging
import os
import re
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

logger = logging.getLogger(__name__)


class UnifiedMemoryType(Enum):
    USER_PREFERENCE = "user_preference"
    RISK_SETTING = "risk_setting"
    TRADING_DECISION = "trading_decision"
    TRADE_RECORD = "trade_record"
    SYSTEM_INSTRUCTION = "system_instruction"
    CONVERSATION = "conversation"
    MARKET_INSIGHT = "market_insight"
    MARKET_DATA = "market_data"
    AI_PREDICTION = "ai_prediction"
    DL_PREDICTION = "dl_prediction"
    RL_OPTIMIZATION = "rl_optimization"
    MODEL_TRAINING = "model_training"
    MODEL_UPDATE = "model_update"
    ONCHAIN_DATA = "onchain_data"
    SOCIAL_SENTIMENT = "social_sentiment"
    NEWS_ANALYSIS = "news_analysis"
    STRATEGY_GENERATED = "strategy_generated"
    LEARNING_SUMMARY = "learning_summary"
    RISK_EVENT = "risk_event"


class MemoryPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    TEMPORARY = 4


@dataclass
class UnifiedMemory:
    id: str
    memory_type: UnifiedMemoryType
    priority: MemoryPriority
    content: str
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    importance_score: float = 0.5
    expires_at: Optional[datetime] = None
    source_module: str = "unknown"
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "memory_type": self.memory_type.value,
            "priority": self.priority.value,
            "content": self.content,
            "summary": self.summary,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count,
            "importance_score": self.importance_score,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source_module": self.source_module,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'UnifiedMemory':
        return cls(
            id=data["id"],
            memory_type=UnifiedMemoryType(data["memory_type"]),
            priority=MemoryPriority(data["priority"]),
            content=data["content"],
            summary=data.get("summary", ""),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None,
            access_count=data.get("access_count", 0),
            importance_score=data.get("importance_score", 0.5),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            source_module=data.get("source_module", "unknown"),
            tags=data.get("tags", [])
        )


class MemoryImportanceEvaluator:
    """记忆重要性评估器"""
    
    CRITICAL_KEYWORDS = [
        "风险", "止损", "爆仓", "亏损", "盈利", "用户偏好",
        "策略优化", "模型更新", "关键支撑", "关键阻力"
    ]
    
    HIGH_VALUE_PATTERNS = [
        r"盈亏[：:]\s*([+-]?\d+\.?\d*)",
        r"胜率[：:]\s*(\d+\.?\d*)%",
        r"策略[：:]\s*(\w+)",
        r"预测[：:]\s*(\w+)",
    ]
    
    GARBAGE_PATTERNS = [
        r"分析以下市场数据",
        r"请提供[：:]",
        r"请以JSON格式返回",
        r"MarketData\(symbol=",
        r"市场趋势分析\n\d\.",
    ]
    
    @classmethod
    def evaluate(cls, content: str, memory_type: UnifiedMemoryType, 
                 metadata: Dict[str, Any] = None) -> Tuple[MemoryPriority, float]:
        """评估记忆重要性和优先级"""
        priority = MemoryPriority.NORMAL
        importance = 0.5
        
        if cls._is_garbage(content):
            return MemoryPriority.TEMPORARY, 0.1
        
        for keyword in cls.CRITICAL_KEYWORDS:
            if keyword in content:
                importance += 0.1
        
        for pattern in cls.HIGH_VALUE_PATTERNS:
            if re.search(pattern, content):
                importance += 0.15
        
        if memory_type in [UnifiedMemoryType.RISK_SETTING, UnifiedMemoryType.RISK_EVENT]:
            priority = MemoryPriority.CRITICAL
            importance = max(importance, 0.9)
        elif memory_type in [UnifiedMemoryType.USER_PREFERENCE, UnifiedMemoryType.SYSTEM_INSTRUCTION]:
            priority = MemoryPriority.HIGH
            importance = max(importance, 0.8)
        elif memory_type in [UnifiedMemoryType.TRADE_RECORD, UnifiedMemoryType.AI_PREDICTION]:
            priority = MemoryPriority.HIGH
            importance = max(importance, 0.7)
        elif memory_type in [UnifiedMemoryType.DL_PREDICTION, UnifiedMemoryType.RL_OPTIMIZATION]:
            priority = MemoryPriority.HIGH
            importance = max(importance, 0.75)
        elif memory_type in [UnifiedMemoryType.MODEL_TRAINING, UnifiedMemoryType.MODEL_UPDATE]:
            priority = MemoryPriority.HIGH
            importance = max(importance, 0.7)
        elif memory_type == UnifiedMemoryType.CONVERSATION:
            priority = MemoryPriority.LOW
            importance = min(importance, 0.4)
        
        if metadata:
            if metadata.get("pnl") and abs(metadata.get("pnl", 0)) > 100:
                importance = min(1.0, importance + 0.2)
            if metadata.get("accuracy") and metadata.get("accuracy") > 0.8:
                importance = min(1.0, importance + 0.1)
        
        importance = max(0.0, min(1.0, importance))
        
        return priority, importance
    
    @classmethod
    def _is_garbage(cls, content: str) -> bool:
        """判断是否为垃圾内容"""
        garbage_count = sum(1 for pattern in cls.GARBAGE_PATTERNS 
                          if re.search(pattern, content))
        return garbage_count >= 2


class UnifiedIntelligentMemory:
    """
    统一智能记忆系统
    
    整合所有记忆功能，与AI模块深度集成
    """
    
    def __init__(self, workspace_path: str = None, storage_path: str = None):
        self.workspace_path = Path(workspace_path) if workspace_path else Path("workspace")
        self.storage_path = Path(storage_path) if storage_path else Path("data/memory")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.memories: Dict[str, UnifiedMemory] = {}
        self.memory_index: Dict[UnifiedMemoryType, List[str]] = {}
        self.workspace_memory: Dict[str, str] = {}
        
        self.config = {
            "max_memories": 2000,
            "auto_cleanup_interval": 3600,
            "importance_threshold": 0.3,
            "expiry_days": {
                MemoryPriority.CRITICAL: 365 * 10,
                MemoryPriority.HIGH: 365,
                MemoryPriority.NORMAL: 90,
                MemoryPriority.LOW: 30,
                MemoryPriority.TEMPORARY: 1
            }
        }
        
        self.workspace_files = [
            "SOUL.md", "IDENTITY.md", "USER.md", "TRADING.md",
            "INSTRUCTIONS.md", "AGENTS.md", "AI_MODELS.md"
        ]
        
        self._load_workspace_memory()
        self._load_memory()
        
        self._is_running = False
        
        logger.info("✅ 统一智能记忆系统初始化完成")
    
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
        memory_file = self.storage_path / "unified_memory.json"
        if not memory_file.exists():
            return
        
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for mem_data in data.get("memories", []):
                try:
                    memory = UnifiedMemory.from_dict(mem_data)
                    if memory.expires_at and memory.expires_at < datetime.now():
                        continue
                    
                    self.memories[memory.id] = memory
                    
                    if memory.memory_type not in self.memory_index:
                        self.memory_index[memory.memory_type] = []
                    self.memory_index[memory.memory_type].append(memory.id)
                except Exception as e:
                    logger.warning(f"加载记忆失败: {e}")
            
            logger.info(f"📂 加载记忆: {len(self.memories)} 条")
            
        except Exception as e:
            logger.error(f"加载记忆文件失败: {e}")
    
    def _save_memory(self) -> None:
        """保存记忆到文件"""
        memory_file = self.storage_path / "unified_memory.json"
        
        try:
            data = {
                "memories": [m.to_dict() for m in self.memories.values()],
                "updated_at": datetime.now().isoformat(),
                "stats": {
                    "total_count": len(self.memories),
                    "type_counts": {t.value: len(ids) for t, ids in self.memory_index.items()}
                }
            }
            
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")
    
    async def start_auto_cleanup(self):
        """启动自动清理任务"""
        if self._is_running:
            return
        
        self._is_running = True
        asyncio.create_task(self._auto_cleanup_loop())
        logger.info("🧹 自动记忆清理任务已启动")
    
    async def stop_auto_cleanup(self):
        """停止自动清理任务"""
        self._is_running = False
        logger.info("自动记忆清理任务已停止")
    
    async def _auto_cleanup_loop(self):
        """自动清理循环"""
        while self._is_running:
            try:
                await asyncio.sleep(self.config["auto_cleanup_interval"])
                await self.cleanup_memories()
            except Exception as e:
                logger.error(f"自动清理出错: {e}")
    
    async def cleanup_memories(self) -> Dict[str, int]:
        """清理过期和低价值记忆"""
        stats = {
            "expired": 0,
            "low_importance": 0,
            "garbage": 0,
            "duplicates": 0
        }
        
        now = datetime.now()
        to_remove = []
        
        content_hashes: Dict[str, str] = {}
        
        for memory_id, memory in self.memories.items():
            if memory.expires_at and memory.expires_at < now:
                to_remove.append(memory_id)
                stats["expired"] += 1
                continue
            
            if memory.importance_score < self.config["importance_threshold"]:
                if memory.priority == MemoryPriority.TEMPORARY:
                    to_remove.append(memory_id)
                    stats["low_importance"] += 1
                    continue
            
            if memory.priority == MemoryPriority.TEMPORARY:
                age_hours = (now - memory.created_at).total_seconds() / 3600
                if age_hours > 24:
                    to_remove.append(memory_id)
                    stats["garbage"] += 1
                    continue
            
            content_hash = hashlib.md5(memory.content.encode()).hexdigest()
            if content_hash in content_hashes:
                to_remove.append(memory_id)
                stats["duplicates"] += 1
            else:
                content_hashes[content_hash] = memory_id
        
        for memory_id in to_remove:
            self._remove_memory(memory_id)
        
        if sum(stats.values()) > 0:
            logger.info(f"🧹 清理记忆: 过期={stats['expired']}, 低价值={stats['low_importance']}, "
                       f"垃圾={stats['garbage']}, 重复={stats['duplicates']}")
            self._save_memory()
        
        return stats
    
    def _remove_memory(self, memory_id: str):
        """移除记忆"""
        if memory_id not in self.memories:
            return
        
        memory = self.memories[memory_id]
        
        if memory.memory_type in self.memory_index:
            if memory_id in self.memory_index[memory.memory_type]:
                self.memory_index[memory.memory_type].remove(memory_id)
        
        del self.memories[memory_id]
    
    async def add_memory(
        self,
        memory_type: UnifiedMemoryType,
        content: str,
        summary: str = "",
        metadata: Dict[str, Any] = None,
        source_module: str = "unknown",
        tags: List[str] = None,
        priority: MemoryPriority = None,
        importance: float = None
    ) -> Optional[str]:
        """添加记忆"""
        
        if MemoryImportanceEvaluator._is_garbage(content):
            logger.debug(f"过滤垃圾记忆: {content[:50]}...")
            return None
        
        if priority is None or importance is None:
            evaluated_priority, evaluated_importance = MemoryImportanceEvaluator.evaluate(
                content, memory_type, metadata
            )
            priority = priority or evaluated_priority
            importance = importance or evaluated_importance
        
        if importance < self.config["importance_threshold"] and priority == MemoryPriority.TEMPORARY:
            return None
        
        memory_id = f"mem_{memory_type.value}_{datetime.now().timestamp()}"
        
        expiry_days = self.config["expiry_days"].get(priority, 90)
        expires_at = datetime.now() + timedelta(days=expiry_days)
        
        memory = UnifiedMemory(
            id=memory_id,
            memory_type=memory_type,
            priority=priority,
            content=content,
            summary=summary or content[:200],
            metadata=metadata or {},
            importance_score=importance,
            expires_at=expires_at,
            source_module=source_module,
            tags=tags or []
        )
        
        self.memories[memory_id] = memory
        
        if memory_type not in self.memory_index:
            self.memory_index[memory_type] = []
        self.memory_index[memory_type].append(memory_id)
        
        self._check_capacity()
        self._save_memory()
        
        logger.debug(f"💾 添加记忆 [{memory_type.value}]: {summary or content[:50]}...")
        return memory_id
    
    def _check_capacity(self):
        """检查容量并清理"""
        if len(self.memories) > self.config["max_memories"]:
            self._evict_low_priority_memories()
    
    def _evict_low_priority_memories(self):
        """驱逐低优先级记忆"""
        target_count = int(self.config["max_memories"] * 0.8)
        
        sorted_memories = sorted(
            self.memories.values(),
            key=lambda m: (m.priority.value, m.importance_score, m.access_count)
        )
        
        to_remove = sorted_memories[:len(self.memories) - target_count]
        
        for memory in to_remove:
            self._remove_memory(memory.id)
        
        if to_remove:
            logger.info(f"🗑️ 驱逐 {len(to_remove)} 条低优先级记忆")
    
    async def add_ai_prediction(
        self,
        prediction_type: str,
        symbol: str,
        prediction: Dict[str, Any],
        confidence: float,
        model_info: Dict[str, Any] = None
    ) -> Optional[str]:
        """添加AI预测记忆"""
        memory_type = UnifiedMemoryType.DL_PREDICTION if "deep_learning" in prediction_type else UnifiedMemoryType.AI_PREDICTION
        
        summary = f"{symbol} {prediction_type}预测: {prediction.get('direction', 'N/A')} (置信度: {confidence:.2%})"
        
        content = json.dumps({
            "prediction_type": prediction_type,
            "symbol": symbol,
            "prediction": prediction,
            "confidence": confidence,
            "model_info": model_info,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
        
        return await self.add_memory(
            memory_type=memory_type,
            content=content,
            summary=summary,
            metadata={
                "symbol": symbol,
                "confidence": confidence,
                "prediction_type": prediction_type
            },
            source_module="ai_prediction",
            tags=[symbol, prediction_type]
        )
    
    async def add_rl_optimization(
        self,
        strategy_name: str,
        old_params: Dict[str, Any],
        new_params: Dict[str, Any],
        improvement: float,
        reason: str = ""
    ) -> Optional[str]:
        """添加强化学习优化记忆"""
        summary = f"策略优化 [{strategy_name}]: 改进 {improvement:.2%}"
        
        content = json.dumps({
            "strategy_name": strategy_name,
            "old_params": old_params,
            "new_params": new_params,
            "improvement": improvement,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
        
        return await self.add_memory(
            memory_type=UnifiedMemoryType.RL_OPTIMIZATION,
            content=content,
            summary=summary,
            metadata={
                "strategy_name": strategy_name,
                "improvement": improvement
            },
            source_module="rl_optimizer",
            tags=[strategy_name, "optimization"]
        )
    
    async def add_model_training(
        self,
        model_id: str,
        model_type: str,
        metrics: Dict[str, float],
        training_config: Dict[str, Any] = None
    ) -> Optional[str]:
        """添加模型训练记忆"""
        summary = f"模型训练 [{model_type}]: {model_id}"
        
        content = json.dumps({
            "model_id": model_id,
            "model_type": model_type,
            "metrics": metrics,
            "training_config": training_config,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
        
        return await self.add_memory(
            memory_type=UnifiedMemoryType.MODEL_TRAINING,
            content=content,
            summary=summary,
            metadata={
                "model_id": model_id,
                "model_type": model_type,
                "metrics": metrics
            },
            source_module="model_training",
            tags=[model_type, model_id]
        )
    
    async def add_model_update(
        self,
        model_id: str,
        update_type: str,
        old_version: str,
        new_version: str,
        performance_change: Dict[str, float]
    ) -> Optional[str]:
        """添加模型更新记忆"""
        summary = f"模型更新 [{model_id}]: {old_version} -> {new_version}"
        
        content = json.dumps({
            "model_id": model_id,
            "update_type": update_type,
            "old_version": old_version,
            "new_version": new_version,
            "performance_change": performance_change,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
        
        return await self.add_memory(
            memory_type=UnifiedMemoryType.MODEL_UPDATE,
            content=content,
            summary=summary,
            metadata={
                "model_id": model_id,
                "update_type": update_type
            },
            source_module="model_updater",
            tags=[model_id, update_type]
        )
    
    async def add_market_sentiment(
        self,
        symbol: str,
        sentiment_data: Dict[str, Any],
        sources: List[str]
    ) -> Optional[str]:
        """添加市场情绪记忆"""
        overall = sentiment_data.get("overall_sentiment", 0.5)
        summary = f"{symbol} 市场情绪: {overall:.2f} (来源: {', '.join(sources)})"
        
        content = json.dumps({
            "symbol": symbol,
            "sentiment_data": sentiment_data,
            "sources": sources,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
        
        return await self.add_memory(
            memory_type=UnifiedMemoryType.SOCIAL_SENTIMENT,
            content=content,
            summary=summary,
            metadata={
                "symbol": symbol,
                "overall_sentiment": overall
            },
            source_module="third_party_data",
            tags=[symbol, "sentiment"] + sources
        )
    
    async def add_onchain_data(
        self,
        symbol: str,
        onchain_metrics: Dict[str, Any],
        insights: str = ""
    ) -> Optional[str]:
        """添加链上数据记忆"""
        summary = f"{symbol} 链上数据: {insights[:100] if insights else '已更新'}"
        
        content = json.dumps({
            "symbol": symbol,
            "onchain_metrics": onchain_metrics,
            "insights": insights,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
        
        return await self.add_memory(
            memory_type=UnifiedMemoryType.ONCHAIN_DATA,
            content=content,
            summary=summary,
            metadata={
                "symbol": symbol
            },
            source_module="onchain_integrator",
            tags=[symbol, "onchain"]
        )
    
    async def add_trade_record(
        self,
        symbol: str,
        action: str,
        price: float,
        quantity: float,
        pnl: float = None,
        reason: str = "",
        strategy: str = ""
    ) -> Optional[str]:
        """添加交易记录"""
        if pnl is not None:
            summary = f"{action} {symbol} @ {price}, 盈亏: {pnl:+.2f}"
        else:
            summary = f"{action} {symbol} @ {price}, 数量: {quantity}"
        
        content = json.dumps({
            "symbol": symbol,
            "action": action,
            "price": price,
            "quantity": quantity,
            "pnl": pnl,
            "reason": reason,
            "strategy": strategy,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
        
        return await self.add_memory(
            memory_type=UnifiedMemoryType.TRADE_RECORD,
            content=content,
            summary=summary,
            metadata={
                "symbol": symbol,
                "action": action,
                "pnl": pnl
            },
            source_module="trading_engine",
            tags=[symbol, action]
        )
    
    async def retrieve_memories(
        self,
        query: str = "",
        memory_types: List[UnifiedMemoryType] = None,
        tags: List[str] = None,
        min_importance: float = 0.0,
        limit: int = 10
    ) -> List[UnifiedMemory]:
        """检索记忆"""
        candidates = list(self.memories.values())
        
        if memory_types:
            candidates = [m for m in candidates if m.memory_type in memory_types]
        
        if tags:
            candidates = [m for m in candidates if any(tag in m.tags for tag in tags)]
        
        if min_importance > 0:
            candidates = [m for m in candidates if m.importance_score >= min_importance]
        
        scored = []
        query_lower = query.lower() if query else ""
        
        for memory in candidates:
            score = memory.importance_score
            
            if query_lower:
                if query_lower in memory.content.lower():
                    score += 0.3
                if query_lower in memory.summary.lower():
                    score += 0.2
                for tag in memory.tags:
                    if query_lower in tag.lower():
                        score += 0.1
            
            age_days = (datetime.now() - memory.created_at).total_seconds() / 86400
            recency_bonus = max(0, 0.2 * (1 - age_days / 30))
            score += recency_bonus
            
            score += min(0.1, memory.access_count * 0.01)
            
            score -= memory.priority.value * 0.05
            
            scored.append((score, memory))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        result = [m for _, m in scored[:limit]]
        
        for memory in result:
            memory.access_count += 1
            memory.last_accessed = datetime.now()
        
        return result
    
    async def get_trading_context(self, symbol: str = None) -> str:
        """获取交易上下文"""
        context_parts = []
        
        context_parts.append("═══════════════════════════════════════════")
        context_parts.append("📚 【AI智能记忆系统】")
        context_parts.append("═══════════════════════════════════════════")
        
        if "SOUL.md" in self.workspace_memory:
            context_parts.append("\n【核心信念 - SOUL.md】")
            context_parts.append(self.workspace_memory["SOUL.md"][:500])
        
        if "IDENTITY.md" in self.workspace_memory:
            context_parts.append("\n【身份定义 - IDENTITY.md】")
            context_parts.append(self.workspace_memory["IDENTITY.md"][:500])
        
        if "USER.md" in self.workspace_memory:
            context_parts.append("\n【用户信息 - USER.md】")
            context_parts.append(self.workspace_memory["USER.md"][:500])
        
        user_prefs = await self.retrieve_memories(
            memory_types=[UnifiedMemoryType.USER_PREFERENCE, UnifiedMemoryType.RISK_SETTING],
            min_importance=0.6,
            limit=10
        )
        if user_prefs:
            context_parts.append("\n👤 【用户偏好和风险设置】:")
            for mem in user_prefs:
                context_parts.append(f"  - {mem.summary}")
        
        if symbol:
            symbol_predictions = await self.retrieve_memories(
                query=symbol,
                memory_types=[UnifiedMemoryType.AI_PREDICTION, UnifiedMemoryType.DL_PREDICTION],
                limit=5
            )
            if symbol_predictions:
                context_parts.append(f"\n🤖 【{symbol} AI预测记录】:")
                for mem in symbol_predictions:
                    context_parts.append(f"  - {mem.summary}")
            
            symbol_sentiment = await self.retrieve_memories(
                query=symbol,
                memory_types=[UnifiedMemoryType.SOCIAL_SENTIMENT, UnifiedMemoryType.ONCHAIN_DATA],
                limit=3
            )
            if symbol_sentiment:
                context_parts.append(f"\n📊 【{symbol} 市场数据记忆】:")
                for mem in symbol_sentiment:
                    context_parts.append(f"  - {mem.summary}")
        
        recent_trades = await self.retrieve_memories(
            memory_types=[UnifiedMemoryType.TRADE_RECORD],
            limit=5
        )
        if recent_trades:
            context_parts.append("\n💹 【最近交易记录】:")
            for mem in recent_trades:
                context_parts.append(f"  - {mem.summary}")
        
        rl_optimizations = await self.retrieve_memories(
            memory_types=[UnifiedMemoryType.RL_OPTIMIZATION],
            limit=3
        )
        if rl_optimizations:
            context_parts.append("\n🔧 【策略优化记录】:")
            for mem in rl_optimizations:
                context_parts.append(f"  - {mem.summary}")
        
        model_updates = await self.retrieve_memories(
            memory_types=[UnifiedMemoryType.MODEL_UPDATE],
            limit=3
        )
        if model_updates:
            context_parts.append("\n🔄 【模型更新记录】:")
            for mem in model_updates:
                context_parts.append(f"  - {mem.summary}")
        
        context_parts.append("\n═══════════════════════════════════════════")
        
        return "\n".join(context_parts)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        type_counts = {}
        priority_counts = {}
        
        for memory in self.memories.values():
            mt = memory.memory_type.value
            type_counts[mt] = type_counts.get(mt, 0) + 1
            
            pr = memory.priority.name
            priority_counts[pr] = priority_counts.get(pr, 0) + 1
        
        return {
            "total_memories": len(self.memories),
            "type_counts": type_counts,
            "priority_counts": priority_counts,
            "workspace_files": list(self.workspace_memory.keys()),
            "avg_importance": np.mean([m.importance_score for m in self.memories.values()]) if self.memories else 0,
            "total_access_count": sum(m.access_count for m in self.memories.values())
        }
    
    async def update_workspace_file(self, filename: str, content: str) -> bool:
        """更新工作区文件"""
        if filename not in self.workspace_files:
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
    
    async def export_for_llm(self, max_tokens: int = 4000) -> str:
        """导出记忆供LLM使用"""
        context = await self.get_trading_context()
        
        if len(context) > max_tokens * 4:
            context = context[:max_tokens * 4]
        
        return context


_unified_memory_instance: Optional[UnifiedIntelligentMemory] = None


def get_unified_memory(workspace_path: str = None, 
                       storage_path: str = None) -> UnifiedIntelligentMemory:
    """获取统一记忆系统单例"""
    global _unified_memory_instance
    
    if _unified_memory_instance is None:
        _unified_memory_instance = UnifiedIntelligentMemory(workspace_path, storage_path)
    
    return _unified_memory_instance
