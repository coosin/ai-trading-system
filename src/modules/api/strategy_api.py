"""
策略API

提供策略管理和信号生成的API接口
"""

import logging
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException

from ..strategies.multi_strategy_manager import MultiStrategyManager
from ..strategies.moving_average import MovingAverageStrategy
from ..strategies.rsi_strategy import RSIStrategy
from ..strategies.bb_strategy import BBStrategy
from ..strategies.macd_strategy import MACDStrategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

# 全局策略管理器实例
strategy_manager: MultiStrategyManager = None

def init_strategy_api(manager: MultiStrategyManager):
    """初始化策略API
    
    Args:
        manager: 策略管理器实例
    """
    global strategy_manager
    strategy_manager = manager


@router.get("/list")
def get_strategies() -> Dict[str, Any]:
    """获取所有策略
    
    Returns:
        策略列表
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="策略管理器未初始化")
    
    return {
        "strategies": strategy_manager.get_all_strategies(),
        "active_strategies": strategy_manager.get_active_strategies(),
        "best_strategy": strategy_manager.get_best_strategy()
    }


@router.get("/performance")
def get_strategy_performance() -> Dict[str, Any]:
    """获取策略性能
    
    Returns:
        策略性能指标
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="策略管理器未初始化")
    
    return strategy_manager.get_strategy_performance()


@router.post("/activate/{strategy_name}")
def activate_strategy(strategy_name: str) -> Dict[str, Any]:
    """激活策略
    
    Args:
        strategy_name: 策略名称
        
    Returns:
        操作结果
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="策略管理器未初始化")
    
    try:
        strategy_manager.activate_strategy(strategy_name)
        return {"status": "success", "message": f"策略 {strategy_name} 已激活"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deactivate/{strategy_name}")
def deactivate_strategy(strategy_name: str) -> Dict[str, Any]:
    """停用策略
    
    Args:
        strategy_name: 策略名称
        
    Returns:
        操作结果
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="策略管理器未初始化")
    
    try:
        strategy_manager.deactivate_strategy(strategy_name)
        return {"status": "success", "message": f"策略 {strategy_name} 已停用"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/update/{strategy_name}")
def update_strategy(strategy_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """更新策略参数
    
    Args:
        strategy_name: 策略名称
        params: 新的参数
        
    Returns:
        操作结果
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="策略管理器未初始化")
    
    try:
        strategy_manager.update_strategy_parameters(strategy_name, params)
        return {"status": "success", "message": f"策略 {strategy_name} 参数已更新"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/add")
def add_strategy(strategy_config: Dict[str, Any]) -> Dict[str, Any]:
    """添加策略
    
    Args:
        strategy_config: 策略配置
        
    Returns:
        操作结果
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="策略管理器未初始化")
    
    try:
        strategy_type = strategy_config.get("type")
        if strategy_type == "moving_average":
            strategy = MovingAverageStrategy(strategy_config)
        elif strategy_type == "rsi":
            strategy = RSIStrategy(strategy_config)
        elif strategy_type == "bb":
            strategy = BBStrategy(strategy_config)
        elif strategy_type == "macd":
            strategy = MACDStrategy(strategy_config)
        else:
            raise HTTPException(status_code=400, detail="不支持的策略类型")
        
        strategy_manager.add_strategy(strategy)
        return {"status": "success", "message": f"策略 {strategy.name} 已添加"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/remove/{strategy_name}")
def remove_strategy(strategy_name: str) -> Dict[str, Any]:
    """移除策略
    
    Args:
        strategy_name: 策略名称
        
    Returns:
        操作结果
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="策略管理器未初始化")
    
    try:
        strategy_manager.remove_strategy(strategy_name)
        return {"status": "success", "message": f"策略 {strategy_name} 已移除"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))