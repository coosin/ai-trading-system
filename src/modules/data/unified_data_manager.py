"""
统一数据管理器

整合所有数据管理功能：
1. 数据质量管理
2. 数据存储管理
3. 数据备份管理
4. 数据管道管理
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

from src.modules.core.module_config_utils import resolve_module_config

logger = logging.getLogger(__name__)


class UnifiedDataManager:
    """
    统一数据管理器
    
    整合所有数据管理功能，提供统一接口
    """
    
    def __init__(self, config: Dict[str, Any] = None, config_manager=None):
        """
        初始化统一数据管理器
        
        Args:
            config: 配置字典
        """
        self.config = resolve_module_config(
            config=config,
            config_manager=config_manager,
            section="unified_data_manager",
            defaults={},
        )
        
        # 子模块（保留现有模块的引用）
        self.quality_checker = None
        self.storage = None
        self.backup = None
        self.pipeline = None
        
        # 数据源注册表
        self.data_sources: Dict[str, Any] = {}
        
        # 数据缓存
        self._cache: Dict[str, Any] = {}
        
        # 统计信息
        self.stats = {
            "total_data_points": 0,
            "total_sources": 0,
            "last_update": None
        }
        
        logger.info("统一数据管理器初始化")
    
    async def initialize(self) -> bool:
        """
        初始化所有子模块
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info("🔧 初始化统一数据管理器...")
            
            # 初始化数据质量检查器
            await self._init_quality_checker()
            
            # 初始化数据存储
            await self._init_storage()
            
            # 初始化数据备份
            await self._init_backup()
            
            # 初始化数据管道
            await self._init_pipeline()
            
            logger.info("✅ 统一数据管理器初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 统一数据管理器初始化失败: {e}")
            return False
    
    async def _init_quality_checker(self):
        """初始化数据质量检查器"""
        try:
            from src.modules.core.enhanced_data_quality import EnhancedDataQualitySystem
            self.quality_checker = EnhancedDataQualitySystem()
            logger.info("✅ 数据质量检查器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 数据质量检查器初始化失败: {e}")
            self.quality_checker = None
    
    async def _init_storage(self):
        """初始化数据存储"""
        try:
            from src.modules.data.enhanced_data_storage import EnhancedDataStorage
            self.storage = EnhancedDataStorage()
            logger.info("✅ 数据存储已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 数据存储初始化失败: {e}")
            self.storage = None
    
    async def _init_backup(self):
        """初始化数据备份"""
        try:
            from src.modules.data.data_backup import DataBackupManager
            self.backup = DataBackupManager()
            logger.info("✅ 数据备份已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 数据备份初始化失败: {e}")
            self.backup = None
    
    async def _init_pipeline(self):
        """初始化数据管道"""
        try:
            # 数据管道功能整合到此管理器
            self.pipeline = {}
            logger.info("✅ 数据管道已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 数据管道初始化失败: {e}")
            self.pipeline = None
    
    # ==================== 数据源管理 ====================
    
    async def register_data_source(self, source_id: str, source_config: Dict[str, Any]) -> bool:
        """
        注册数据源
        
        Args:
            source_id: 数据源ID
            source_config: 数据源配置
        
        Returns:
            bool: 是否成功
        """
        try:
            self.data_sources[source_id] = {
                "config": source_config,
                "registered_at": datetime.now(),
                "status": "active"
            }
            
            self.stats["total_sources"] = len(self.data_sources)
            
            logger.info(f"✅ 数据源已注册: {source_id}")
            return True
            
        except Exception as e:
            logger.error(f"注册数据源失败 {source_id}: {e}")
            return False
    
    async def check_data_source(self, source_id: str) -> Dict[str, Any]:
        """
        检查数据源状态
        
        Args:
            source_id: 数据源ID
        
        Returns:
            Dict: 数据源状态
        """
        try:
            if source_id not in self.data_sources:
                return {"status": "not_found"}
            
            source = self.data_sources[source_id]
            
            # 如果有质量检查器，使用它
            if self.quality_checker:
                try:
                    quality = await self.quality_checker.check_data_source(source_id)
                    return {
                        "status": source["status"],
                        "quality": quality
                    }
                except:
                    pass
            
            return {
                "status": source["status"],
                "registered_at": source["registered_at"].isoformat()
            }
            
        except Exception as e:
            logger.error(f"检查数据源失败 {source_id}: {e}")
            return {"status": "error", "error": str(e)}
    
    # ==================== 数据存储管理 ====================
    
    async def save_market_data(self, symbol: str, data: Dict[str, Any]) -> bool:
        """
        保存市场数据
        
        Args:
            symbol: 交易对
            data: 市场数据
        
        Returns:
            bool: 是否成功
        """
        try:
            # 使用存储模块
            if self.storage:
                try:
                    await self.storage.save_market_data(symbol, data)
                except:
                    pass
            
            # 更新缓存
            cache_key = f"market_data_{symbol}"
            self._cache[cache_key] = {
                "data": data,
                "timestamp": datetime.now()
            }
            
            # 更新统计
            self.stats["total_data_points"] += 1
            self.stats["last_update"] = datetime.now()
            
            logger.debug(f"保存市场数据: {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"保存市场数据失败 {symbol}: {e}")
            return False
    
    async def load_market_data(self, symbol: str, start_time: datetime = None, 
                               end_time: datetime = None) -> List[Dict[str, Any]]:
        """
        加载市场数据
        
        Args:
            symbol: 交易对
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            List[Dict]: 市场数据列表
        """
        try:
            # 先检查缓存
            cache_key = f"market_data_{symbol}"
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if datetime.now() - cached["timestamp"] < timedelta(minutes=5):
                    return [cached["data"]]
            
            # 使用存储模块
            if self.storage:
                try:
                    data = await self.storage.load_market_data(symbol, start_time, end_time)
                    return data
                except:
                    pass
            
            return []
            
        except Exception as e:
            logger.error(f"加载市场数据失败 {symbol}: {e}")
            return []
    
    async def get_data_range(self, symbol: str) -> Dict[str, datetime]:
        """
        获取数据范围
        
        Args:
            symbol: 交易对
        
        Returns:
            Dict: 数据范围
        """
        try:
            if self.storage:
                try:
                    return await self.storage.get_data_range(symbol)
                except:
                    pass
            
            return {}
            
        except Exception as e:
            logger.error(f"获取数据范围失败 {symbol}: {e}")
            return {}
    
    # ==================== 数据备份管理 ====================
    
    async def create_backup(self, backup_name: str = None) -> bool:
        """
        创建备份
        
        Args:
            backup_name: 备份名称
        
        Returns:
            bool: 是否成功
        """
        try:
            if self.backup:
                try:
                    await self.backup.create_backup(backup_name)
                    logger.info(f"✅ 备份已创建: {backup_name}")
                    return True
                except:
                    pass
            
            logger.warning("备份模块未初始化")
            return False
            
        except Exception as e:
            logger.error(f"创建备份失败: {e}")
            return False
    
    async def restore_backup(self, backup_id: str) -> bool:
        """
        恢复备份
        
        Args:
            backup_id: 备份ID
        
        Returns:
            bool: 是否成功
        """
        try:
            if self.backup:
                try:
                    await self.backup.restore_backup(backup_id)
                    logger.info(f"✅ 备份已恢复: {backup_id}")
                    return True
                except:
                    pass
            
            logger.warning("备份模块未初始化")
            return False
            
        except Exception as e:
            logger.error(f"恢复备份失败: {e}")
            return False
    
    async def list_backups(self) -> List[Dict[str, Any]]:
        """
        列出所有备份
        
        Returns:
            List[Dict]: 备份列表
        """
        try:
            if self.backup:
                try:
                    return await self.backup.list_backups()
                except:
                    pass
            
            return []
            
        except Exception as e:
            logger.error(f"列出备份失败: {e}")
            return []
    
    # ==================== 数据管道管理 ====================
    
    async def process_market_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理市场数据
        
        Args:
            data: 市场数据
        
        Returns:
            Dict: 处理结果
        """
        try:
            # 数据质量检查
            if self.quality_checker:
                try:
                    quality_result = await self.quality_checker.check_data_source(data.get("source", "unknown"))
                    data["quality"] = quality_result
                except:
                    pass
            
            # 保存数据
            if "symbol" in data:
                await self.save_market_data(data["symbol"], data)
            
            logger.debug(f"处理市场数据: {data.get('symbol', 'unknown')}")
            return {"status": "success", "data": data}
            
        except Exception as e:
            logger.error(f"处理市场数据失败: {e}")
            return {"status": "error", "error": str(e)}
    
    # ==================== 统计和监控 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        return {
            **self.stats,
            "total_sources": len(self.data_sources),
            "quality_checker_available": self.quality_checker is not None,
            "storage_available": self.storage is not None,
            "backup_available": self.backup is not None,
            "pipeline_available": self.pipeline is not None
        }
    
    # ==================== 清理 ====================
    
    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("清理统一数据管理器...")
            
            # 清理缓存
            self._cache.clear()
            
            # 清理数据源
            self.data_sources.clear()
            
            logger.info("✅ 统一数据管理器清理完成")
        except Exception as e:
            logger.error(f"清理失败: {e}")
