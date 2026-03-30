"""
风险和资金管理API接口

提供资金管理和风险控制相关的API端点
"""

import logging
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Query

from ..risk.资金管理模块 import MoneyManager, RiskLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])

# 全局资金管理器实例
_money_manager = None

def set_money_manager(manager: MoneyManager):
    """设置资金管理器实例"""
    global _money_manager
    _money_manager = manager

@router.get("/portfolio")
async def get_portfolio_info():
    """获取投资组合信息"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    portfolio = _money_manager.get_portfolio_info()
    return {
        "total_equity": portfolio.total_equity,
        "available_balance": portfolio.available_balance,
        "margin_used": portfolio.margin_used,
        "margin_level": portfolio.margin_level,
        "total_exposure": portfolio.total_exposure,
        "leverage": portfolio.leverage
    }

@router.get("/positions")
async def get_positions():
    """获取当前仓位"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    positions = _money_manager.get_positions()
    result = {}
    for symbol, pos in positions.items():
        result[symbol] = {
            "side": pos.side,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "current_price": pos.current_price,
            "pnl": pos.pnl,
            "margin": pos.margin,
            "leverage": pos.leverage
        }
    return result

@router.get("/risk-metrics")
async def get_risk_metrics():
    """获取风险指标"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    metrics = _money_manager.get_risk_metrics()
    return {
        "var_95": metrics.var_95,
        "max_drawdown": metrics.max_drawdown,
        "sharpe_ratio": metrics.sharpe_ratio,
        "sortino_ratio": metrics.sortino_ratio,
        "win_rate": metrics.win_rate,
        "average_win_loss_ratio": metrics.average_win_loss_ratio
    }

@router.get("/equity-curve")
async def get_equity_curve():
    """获取资金曲线"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    equity_curve = _money_manager.get_equity_curve()
    return [{
        "timestamp": t,
        "equity": e
    } for t, e in equity_curve]

@router.get("/drawdown-curve")
async def get_drawdown_curve():
    """获取回撤曲线"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    drawdown_curve = _money_manager.get_drawdown_curve()
    return [{
        "timestamp": t,
        "drawdown": d
    } for t, d in drawdown_curve]

@router.post("/position-size")
async def calculate_position_size(symbol: str, entry_price: float, stop_loss_price: float):
    """计算仓位大小"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    position_size = _money_manager.calculate_position_size(symbol, entry_price, stop_loss_price)
    return {
        "symbol": symbol,
        "entry_price": entry_price,
        "stop_loss_price": stop_loss_price,
        "position_size": position_size
    }

@router.post("/risk-level")
async def set_risk_level(risk_level: str):
    """设置风险等级"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    try:
        new_risk_level = RiskLevel(risk_level)
        _money_manager.adjust_risk_level(new_risk_level)
        return {
            "status": "success",
            "message": f"Risk level set to {risk_level}"
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid risk level")

@router.get("/risk-level")
async def get_risk_level():
    """获取当前风险等级"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    return {
        "risk_level": _money_manager.risk_level.value
    }

@router.get("/recommendations")
async def get_risk_recommendations():
    """获取风险调整建议"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    recommendations = _money_manager.get_risk_adjustment_recommendations()
    return {
        "recommendations": recommendations
    }

@router.post("/update-portfolio")
async def update_portfolio(equity: float, margin_used: float):
    """更新投资组合信息"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    _money_manager.update_portfolio(equity, margin_used)
    return {
        "status": "success",
        "message": "Portfolio updated"
    }

@router.post("/add-position")
async def add_position(symbol: str, side: str, quantity: float, entry_price: float):
    """添加仓位"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    _money_manager.add_position(symbol, side, quantity, entry_price)
    return {
        "status": "success",
        "message": "Position added"
    }

@router.post("/update-position")
async def update_position(symbol: str, current_price: float):
    """更新仓位信息"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    _money_manager.update_position(symbol, current_price)
    return {
        "status": "success",
        "message": "Position updated"
    }

@router.post("/close-position")
async def close_position(symbol: str):
    """关闭仓位"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    _money_manager.close_position(symbol)
    return {
        "status": "success",
        "message": "Position closed"
    }

@router.get("/risk-exceeded")
async def check_risk_exceeded():
    """检查是否超过风险限制"""
    if not _money_manager:
        raise HTTPException(status_code=503, detail="Money manager not initialized")
    
    is_exceeded = _money_manager.is_risk_exceeded()
    return {
        "risk_exceeded": is_exceeded
    }