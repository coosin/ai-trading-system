"""
策略热加载系统

功能：
1. 无需重启即可更新策略逻辑
2. 策略版本管理
3. 策略回滚支持
4. 策略状态持久化
"""

import asyncio
import logging
import hashlib
import importlib
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from enum import Enum
import json

logger = logging.getLogger(__name__)


class StrategyStatus(Enum):
    """策略状态"""
    INACTIVE = "inactive"
    ACTIVE = "active"
    LOADING = "loading"
    ERROR = "error"
    ROLLBACK = "rollback"


@dataclass
class StrategyVersion:
    """策略版本"""
    version_id: str
    strategy_name: str
    code_hash: str
    config: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = False
    performance_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class StrategyInstance:
    """策略实例"""
    name: str
    version: StrategyVersion
    status: StrategyStatus
    module: Optional[Any] = None
    instance: Optional[Any] = None
    error_message: Optional[str] = None
    loaded_at: Optional[datetime] = None
    trade_count: int = 0
    pnl: float = 0.0


class StrategyHotLoader:
    """策略热加载器"""
    
    def __init__(self, strategy_dir: str = "src/modules/strategies"):
        self.strategy_dir = Path(strategy_dir)
        self.strategies: Dict[str, StrategyInstance] = {}
        self.versions: Dict[str, List[StrategyVersion]] = {}
        self.max_versions = 10
        
        self._strategy_watchers: Dict[str, float] = {}
        self._callbacks: Dict[str, List[Callable]] = {
            "on_load": [],
            "on_unload": [],
            "on_error": [],
            "on_rollback": []
        }
        
        self._running = False
    
    async def initialize(self) -> bool:
        """初始化策略热加载器"""
        logger.info("策略热加载器初始化...")
        
        self.strategy_dir.mkdir(parents=True, exist_ok=True)
        
        return True
    
    def register_callback(self, event: str, callback: Callable):
        """注册事件回调"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    async def load_strategy(
        self,
        strategy_name: str,
        strategy_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """加载策略"""
        logger.info(f"加载策略: {strategy_name}")
        
        try:
            if strategy_name in self.strategies:
                old_instance = self.strategies[strategy_name]
                if old_instance.status == StrategyStatus.ACTIVE:
                    await self.unload_strategy(strategy_name)
            
            if strategy_path is None:
                strategy_path = f"src.modules.strategies.{strategy_name}"
            
            code_hash = await self._calculate_code_hash(strategy_path)
            
            version = StrategyVersion(
                version_id=self._generate_version_id(strategy_name, code_hash),
                strategy_name=strategy_name,
                code_hash=code_hash,
                config=config or {}
            )
            
            instance = StrategyInstance(
                name=strategy_name,
                version=version,
                status=StrategyStatus.LOADING
            )
            self.strategies[strategy_name] = instance
            
            module = await self._import_strategy_module(strategy_path)
            
            strategy_class = getattr(module, strategy_name.title().replace("_", ""), None)
            if strategy_class is None:
                strategy_class = getattr(module, "Strategy", None)
            
            if strategy_class is None:
                raise ValueError(f"找不到策略类: {strategy_name}")
            
            strategy_obj = strategy_class(config or {})
            
            if hasattr(strategy_obj, 'initialize'):
                await strategy_obj.initialize()
            
            instance.module = module
            instance.instance = strategy_obj
            instance.status = StrategyStatus.ACTIVE
            instance.loaded_at = datetime.now()
            
            if strategy_name not in self.versions:
                self.versions[strategy_name] = []
            self.versions[strategy_name].append(version)
            
            if len(self.versions[strategy_name]) > self.max_versions:
                self.versions[strategy_name] = self.versions[strategy_name][-self.max_versions:]
            
            await self._notify_callbacks("on_load", strategy_name, instance)
            
            logger.info(f"策略加载成功: {strategy_name} (version: {version.version_id})")
            return True
            
        except Exception as e:
            logger.error(f"策略加载失败: {strategy_name} - {e}")
            
            if strategy_name in self.strategies:
                self.strategies[strategy_name].status = StrategyStatus.ERROR
                self.strategies[strategy_name].error_message = str(e)
            
            await self._notify_callbacks("on_error", strategy_name, str(e))
            return False
    
    async def unload_strategy(self, strategy_name: str) -> bool:
        """卸载策略"""
        logger.info(f"卸载策略: {strategy_name}")
        
        if strategy_name not in self.strategies:
            return True
        
        try:
            instance = self.strategies[strategy_name]
            
            if instance.instance and hasattr(instance.instance, 'cleanup'):
                await instance.instance.cleanup()
            
            instance.status = StrategyStatus.INACTIVE
            instance.instance = None
            instance.module = None
            
            await self._notify_callbacks("on_unload", strategy_name, instance)
            
            del self.strategies[strategy_name]
            
            logger.info(f"策略卸载成功: {strategy_name}")
            return True
            
        except Exception as e:
            logger.error(f"策略卸载失败: {strategy_name} - {e}")
            return False
    
    async def reload_strategy(self, strategy_name: str) -> bool:
        """重新加载策略"""
        logger.info(f"重新加载策略: {strategy_name}")
        
        if strategy_name in self.strategies:
            old_config = self.strategies[strategy_name].version.config
            await self.unload_strategy(strategy_name)
        else:
            old_config = None
        
        return await self.load_strategy(strategy_name, config=old_config)
    
    async def rollback_strategy(self, strategy_name: str, version_id: Optional[str] = None) -> bool:
        """回滚策略到指定版本"""
        logger.info(f"回滚策略: {strategy_name} (version: {version_id})")
        
        if strategy_name not in self.versions or not self.versions[strategy_name]:
            logger.warning(f"没有可回滚的版本: {strategy_name}")
            return False
        
        if version_id is None:
            if len(self.versions[strategy_name]) < 2:
                logger.warning(f"没有历史版本可回滚: {strategy_name}")
                return False
            target_version = self.versions[strategy_name][-2]
        else:
            target_version = None
            for v in self.versions[strategy_name]:
                if v.version_id == version_id:
                    target_version = v
                    break
            
            if target_version is None:
                logger.warning(f"找不到指定版本: {version_id}")
                return False
        
        try:
            await self.unload_strategy(strategy_name)
            
            success = await self.load_strategy(
                strategy_name,
                config=target_version.config
            )
            
            if success:
                self.strategies[strategy_name].status = StrategyStatus.ROLLBACK
                await self._notify_callbacks("on_rollback", strategy_name, target_version)
                logger.info(f"策略回滚成功: {strategy_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"策略回滚失败: {strategy_name} - {e}")
            return False
    
    async def update_strategy_config(
        self,
        strategy_name: str,
        config: Dict[str, Any]
    ) -> bool:
        """更新策略配置"""
        if strategy_name not in self.strategies:
            logger.warning(f"策略不存在: {strategy_name}")
            return False
        
        instance = self.strategies[strategy_name]
        
        if instance.instance and hasattr(instance.instance, 'update_config'):
            try:
                await instance.instance.update_config(config)
                instance.version.config.update(config)
                logger.info(f"策略配置更新成功: {strategy_name}")
                return True
            except Exception as e:
                logger.error(f"策略配置更新失败: {strategy_name} - {e}")
                return False
        else:
            instance.version.config.update(config)
            return True
    
    async def get_strategy(self, strategy_name: str) -> Optional[Any]:
        """获取策略实例"""
        if strategy_name in self.strategies:
            instance = self.strategies[strategy_name]
            if instance.status == StrategyStatus.ACTIVE:
                return instance.instance
        return None
    
    async def list_strategies(self) -> List[Dict[str, Any]]:
        """列出所有策略"""
        result = []
        
        for name, instance in self.strategies.items():
            result.append({
                "name": name,
                "status": instance.status.value,
                "version": instance.version.version_id,
                "loaded_at": instance.loaded_at.isoformat() if instance.loaded_at else None,
                "trade_count": instance.trade_count,
                "pnl": instance.pnl
            })
        
        return result
    
    async def get_strategy_versions(self, strategy_name: str) -> List[Dict[str, Any]]:
        """获取策略版本历史"""
        if strategy_name not in self.versions:
            return []
        
        return [
            {
                "version_id": v.version_id,
                "code_hash": v.code_hash[:8],
                "created_at": v.created_at.isoformat(),
                "is_active": v.is_active,
                "performance": v.performance_metrics
            }
            for v in self.versions[strategy_name]
        ]
    
    async def _import_strategy_module(self, module_path: str):
        """导入策略模块"""
        parts = module_path.split(".")
        module_name = ".".join(parts[:-1]) if len(parts) > 1 else module_path
        
        if module_name in sys.modules:
            module = importlib.reload(sys.modules[module_name])
        else:
            module = importlib.import_module(module_name)
        
        return module
    
    async def _calculate_code_hash(self, module_path: str) -> str:
        """计算代码哈希"""
        try:
            parts = module_path.split(".")
            file_path = Path("/".join(parts) + ".py")
            
            if not file_path.exists():
                file_path = self.strategy_dir / f"{parts[-1]}.py"
            
            if file_path.exists():
                content = file_path.read_text()
                return hashlib.md5(content.encode()).hexdigest()
        except Exception:
            pass
        
        return hashlib.md5(module_path.encode()).hexdigest()
    
    def _generate_version_id(self, strategy_name: str, code_hash: str) -> str:
        """生成版本ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{strategy_name}_{timestamp}_{code_hash[:8]}"
    
    async def _notify_callbacks(self, event: str, *args):
        """通知回调"""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args)
                else:
                    callback(*args)
            except Exception as e:
                logger.error(f"回调执行失败: {event} - {e}")
    
    async def update_strategy_metrics(
        self,
        strategy_name: str,
        trade_count: int = 0,
        pnl: float = 0.0
    ):
        """更新策略指标"""
        if strategy_name in self.strategies:
            instance = self.strategies[strategy_name]
            instance.trade_count += trade_count
            instance.pnl += pnl
    
    async def cleanup(self):
        """清理资源"""
        self._running = False
        
        for strategy_name in list(self.strategies.keys()):
            await self.unload_strategy(strategy_name)
        
        logger.info("策略热加载器清理完成")
