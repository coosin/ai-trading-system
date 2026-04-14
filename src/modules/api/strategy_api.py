"""
策略API

提供策略管理和信号生成的API接口
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ..core.strategy_manager import StrategyManager
from ..strategies.moving_average import MovingAverageStrategy
from ..strategies.rsi_strategy import RSIStrategy
from ..strategies.bb_strategy import BBStrategy
from ..strategies.macd_strategy import MACDStrategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

# 全局策略管理器实例
strategy_manager: StrategyManager = None

def init_strategy_api(manager: StrategyManager):
    """初始化策略API
    
    Args:
        manager: 策略管理器实例
    """
    global strategy_manager
    strategy_manager = manager


def _strategy_list_items(manager: StrategyManager) -> List[Dict[str, Any]]:
    """与 server.py 中 /api/v1/strategies 一致的列表结构（StrategyManager 真实字段）。"""
    configs = getattr(manager, "strategy_configs", None) or {}
    metrics = getattr(manager, "performance_metrics", None) or {}
    out: List[Dict[str, Any]] = []
    for sid, cfg in configs.items():
        d = cfg.to_dict() if hasattr(cfg, "to_dict") else {}
        item: Dict[str, Any] = {
            "id": d.get("strategy_id", sid),
            "strategy_id": d.get("strategy_id", sid),
            "name": d.get("name", sid),
            "description": d.get("description", ""),
            "strategy_type": d.get("strategy_type"),
            "status": "active" if d.get("enabled", True) else "inactive",
            "enabled": d.get("enabled", True),
            "symbols": d.get("symbols", []),
            "timeframe": d.get("timeframe", "1h"),
            "parameters": d.get("parameters", {}),
            "metadata": d.get("metadata", {}),
            "returns": "-",
            "max_drawdown": "-",
            "sharpe_ratio": "-",
        }
        perf = metrics.get(sid)
        if perf:
            item["total_trades"] = int(getattr(perf, "total_trades", 0) or 0)
            item["win_rate"] = round(100.0 * float(getattr(perf, "win_rate", 0.0) or 0.0), 2)
            item["max_drawdown"] = str(
                round(float(getattr(perf, "max_drawdown", 0.0) or 0.0) * 100.0, 2)
            )
            item["sharpe_ratio"] = str(round(float(getattr(perf, "sharpe_ratio", 0.0) or 0.0), 3))
            item["returns"] = str(round(float(getattr(perf, "total_pnl", 0.0) or 0.0), 4))
        out.append(item)
    return out


def _performance_payload(manager: StrategyManager) -> Dict[str, Any]:
    """汇总 performance_metrics，避免调用已删除的同步 API。"""
    metrics = getattr(manager, "performance_metrics", None) or {}
    by_id: Dict[str, Any] = {}
    for sid, perf in metrics.items():
        mr = getattr(perf, "market_regime", None)
        mr_val = mr.value if mr is not None and hasattr(mr, "value") else mr
        lu = getattr(perf, "last_updated", None)
        by_id[sid] = {
            "strategy_id": getattr(perf, "strategy_id", sid),
            "total_pnl": float(getattr(perf, "total_pnl", 0.0) or 0.0),
            "total_trades": int(getattr(perf, "total_trades", 0) or 0),
            "winning_trades": int(getattr(perf, "winning_trades", 0) or 0),
            "losing_trades": int(getattr(perf, "losing_trades", 0) or 0),
            "win_rate": float(getattr(perf, "win_rate", 0.0) or 0.0),
            "sharpe_ratio": float(getattr(perf, "sharpe_ratio", 0.0) or 0.0),
            "max_drawdown": float(getattr(perf, "max_drawdown", 0.0) or 0.0),
            "market_regime": mr_val,
            "last_updated": lu.isoformat() if lu is not None else None,
        }
    regime = getattr(manager, "market_regime", None)
    regime_val = regime.value if regime is not None and hasattr(regime, "value") else regime
    return {
        "strategies": by_id,
        "best_strategy": getattr(manager, "best_strategy", None),
        "market_regime": regime_val,
        "strategy_config_count": len(getattr(manager, "strategy_configs", None) or {}),
    }


@router.get("/list")
def get_strategies() -> Dict[str, Any]:
    """获取所有策略
    
    Returns:
        策略列表
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="策略管理器未初始化")

    items = _strategy_list_items(strategy_manager)
    active = [x for x in items if x.get("enabled", True)]
    return {
        "strategies": items,
        "active_strategies": active,
        "best_strategy": getattr(strategy_manager, "best_strategy", None),
    }


@router.get("/performance")
def get_strategy_performance() -> Dict[str, Any]:
    """获取策略性能
    
    Returns:
        策略性能指标
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="策略管理器未初始化")

    return _performance_payload(strategy_manager)


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