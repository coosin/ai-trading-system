"""
记忆迁移工具
将旧的记忆数据迁移到统一记忆系统
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .unified_intelligent_memory import (
    UnifiedIntelligentMemory,
    UnifiedMemoryType,
    MemoryPriority,
    MemoryImportanceEvaluator
)

logger = logging.getLogger(__name__)


class MemoryMigrator:
    """记忆迁移器"""
    
    TYPE_MAPPING = {
        "short_term": UnifiedMemoryType.CONVERSATION,
        "long_term": UnifiedMemoryType.MARKET_INSIGHT,
        "trade_history": UnifiedMemoryType.TRADE_RECORD,
        "user_preference": UnifiedMemoryType.USER_PREFERENCE,
        "system_instruction": UnifiedMemoryType.SYSTEM_INSTRUCTION,
        "user_preference": UnifiedMemoryType.USER_PREFERENCE,
        "risk_setting": UnifiedMemoryType.RISK_SETTING,
        "trading_decision": UnifiedMemoryType.TRADING_DECISION,
        "conversation": UnifiedMemoryType.CONVERSATION,
        "market_insight": UnifiedMemoryType.MARKET_INSIGHT,
        "learning": UnifiedMemoryType.LEARNING_SUMMARY,
        "trade_open": UnifiedMemoryType.TRADE_RECORD,
        "trade_close": UnifiedMemoryType.TRADE_RECORD,
        "pnl_record": UnifiedMemoryType.TRADE_RECORD,
        "strategy_optimization": UnifiedMemoryType.RL_OPTIMIZATION,
        "risk_event": UnifiedMemoryType.RISK_EVENT,
    }
    
    PRIORITY_MAPPING = {
        0: MemoryPriority.CRITICAL,
        1: MemoryPriority.HIGH,
        2: MemoryPriority.NORMAL,
        3: MemoryPriority.LOW,
        4: MemoryPriority.TEMPORARY,
    }
    
    def __init__(self, storage_path: str = "data/memory"):
        self.storage_path = Path(storage_path)
        self.stats = {
            "total_source": 0,
            "migrated": 0,
            "filtered": 0,
            "errors": 0
        }
    
    async def migrate_all(self, target_memory: UnifiedIntelligentMemory) -> Dict[str, int]:
        """迁移所有旧记忆数据"""
        logger.info("开始记忆迁移...")
        
        await self._migrate_ai_memory(target_memory)
        
        await self._migrate_enhanced_memory(target_memory)
        
        await self._cleanup_after_migration()
        
        logger.info(f"迁移完成: {self.stats}")
        return self.stats
    
    async def _migrate_ai_memory(self, target: UnifiedIntelligentMemory):
        """迁移 ai_memory.py 格式的记忆"""
        memory_file = self.storage_path / "ai_memory.json"
        if not memory_file.exists():
            return
        
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for item in data.get("short_term", []):
                self.stats["total_source"] += 1
                await self._migrate_single_item(target, item, "short_term")
            
            for item in data.get("long_term", []):
                self.stats["total_source"] += 1
                await self._migrate_single_item(target, item, item.get("memory_type", "long_term"))
                
        except Exception as e:
            logger.error(f"迁移ai_memory失败: {e}")
            self.stats["errors"] += 1
    
    async def _migrate_enhanced_memory(self, target: UnifiedIntelligentMemory):
        """迁移 enhanced_memory_manager.py 格式的记忆"""
        memory_file = self.storage_path / "enhanced_memory.json"
        if not memory_file.exists():
            return
        
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for item in data.get("short_term", []):
                self.stats["total_source"] += 1
                await self._migrate_single_item(target, item, "short_term")
            
            for item in data.get("long_term", []):
                self.stats["total_source"] += 1
                category = item.get("category", "long_term")
                await self._migrate_single_item(target, item, category)
                
        except Exception as e:
            logger.error(f"迁移enhanced_memory失败: {e}")
            self.stats["errors"] += 1
    
    async def _migrate_single_item(
        self, 
        target: UnifiedIntelligentMemory, 
        item: Dict[str, Any],
        source_type: str
    ):
        """迁移单个记忆条目"""
        try:
            content = item.get("content", "")
            if not content:
                self.stats["filtered"] += 1
                return
            
            if MemoryImportanceEvaluator._is_garbage(content):
                self.stats["filtered"] += 1
                return
            
            memory_type = self.TYPE_MAPPING.get(source_type, UnifiedMemoryType.MARKET_INSIGHT)
            
            priority_val = item.get("priority", 2)
            if isinstance(priority_val, int):
                priority = self.PRIORITY_MAPPING.get(priority_val, MemoryPriority.NORMAL)
            else:
                priority = MemoryPriority.NORMAL
            
            metadata = item.get("metadata", item.get("trade", {}))
            
            _, importance = MemoryImportanceEvaluator.evaluate(content, memory_type, metadata)
            
            created_at = item.get("created_at") or item.get("timestamp")
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except:
                    created_at = datetime.now()
            else:
                created_at = datetime.now()
            
            memory_id = await target.add_memory(
                memory_type=memory_type,
                content=content,
                summary=item.get("summary", content[:200]),
                metadata=metadata,
                priority=priority,
                importance=importance,
                source_module="migration",
                tags=item.get("tags", [])
            )
            
            if memory_id:
                self.stats["migrated"] += 1
            else:
                self.stats["filtered"] += 1
                
        except Exception as e:
            logger.warning(f"迁移单条记忆失败: {e}")
            self.stats["errors"] += 1
    
    async def _cleanup_after_migration(self):
        """迁移后清理"""
        backup_dir = self.storage_path / "backup"
        backup_dir.mkdir(exist_ok=True)
        
        for filename in ["ai_memory.json", "enhanced_memory.json"]:
            src = self.storage_path / filename
            if src.exists():
                import shutil
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dst = backup_dir / f"{filename}.{timestamp}.bak"
                shutil.move(str(src), str(dst))
                logger.info(f"备份旧记忆文件: {filename} -> {dst}")


async def run_migration():
    """运行记忆迁移"""
    from .unified_intelligent_memory import get_unified_memory
    
    memory = get_unified_memory()
    migrator = MemoryMigrator()
    
    stats = await migrator.migrate_all(memory)
    
    print(f"\n迁移统计:")
    print(f"  源记忆总数: {stats['total_source']}")
    print(f"  成功迁移: {stats['migrated']}")
    print(f"  过滤丢弃: {stats['filtered']}")
    print(f"  错误数量: {stats['errors']}")
    
    return stats


if __name__ == "__main__":
    asyncio.run(run_migration())
