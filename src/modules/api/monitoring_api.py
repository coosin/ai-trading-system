"""
监控系统API接口

提供交易监控相关的API端点
"""

import logging
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Query

from ..monitoring.trading_monitor import TradingMonitor, TradingAlert, TradeExecution, StrategyPerformance, MarketDataStatus, RiskMetrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])

# 全局监控器实例
_trading_monitor = None

def set_trading_monitor(monitor: TradingMonitor):
    """设置交易监控器实例"""
    global _trading_monitor
    _trading_monitor = monitor

@router.get("/summary")
async def get_monitoring_summary():
    """获取监控摘要"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    return _trading_monitor.get_monitoring_summary()

@router.get("/alerts")
async def get_active_alerts():
    """获取活跃告警"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    alerts = _trading_monitor.get_active_alerts()
    return [{
        "alert_id": alert.alert_id,
        "timestamp": alert.timestamp,
        "severity": alert.severity.value,
        "alert_type": alert.alert_type,
        "message": alert.message,
        "details": alert.details
    } for alert in alerts]

@router.get("/alerts/history")
async def get_alert_history(limit: int = Query(50, description="返回的历史记录数量")):
    """获取告警历史"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    alerts = _trading_monitor.get_alert_history(limit)
    return [{
        "alert_id": alert.alert_id,
        "timestamp": alert.timestamp,
        "severity": alert.severity.value,
        "alert_type": alert.alert_type,
        "message": alert.message,
        "details": alert.details,
        "resolved": alert.resolved
    } for alert in alerts]

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """解决告警"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    _trading_monitor.resolve_alert(alert_id)
    return {"status": "success", "message": "Alert resolved"}

@router.get("/trades")
async def get_trade_history(limit: int = Query(50, description="返回的交易记录数量")):
    """获取交易历史"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    trades = _trading_monitor.get_trade_history(limit)
    return [{
        "order_id": trade.order_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": trade.price,
        "status": trade.status.value,
        "timestamp": trade.timestamp,
        "executed_quantity": trade.executed_quantity,
        "avg_price": trade.avg_price,
        "fee": trade.fee
    } for trade in trades]

@router.get("/strategies")
async def get_strategy_performance():
    """获取策略性能"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    performance = _trading_monitor.get_strategy_performance()
    result = {}
    for strategy_name, perf in performance.items():
        result[strategy_name] = {
            "total_trades": perf.total_trades,
            "win_trades": perf.win_trades,
            "loss_trades": perf.loss_trades,
            "win_rate": perf.win_rate,
            "total_pnl": perf.total_pnl,
            "max_drawdown": perf.max_drawdown,
            "sharpe_ratio": perf.sharpe_ratio,
            "last_update": perf.last_update
        }
    return result

@router.get("/market-data")
async def get_market_data_status():
    """获取市场数据状态"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    market_data = _trading_monitor.get_market_data_status()
    result = {}
    for symbol, data in market_data.items():
        result[symbol] = {
            "last_price": data.last_price,
            "volume": data.volume,
            "bid": data.bid,
            "ask": data.ask,
            "spread": data.spread,
            "last_update": data.last_update,
            "data_age": data.data_age
        }
    return result

@router.get("/risk")
async def get_risk_metrics():
    """获取风险指标"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    risk_metrics = _trading_monitor.get_risk_metrics()
    if risk_metrics:
        return {
            "portfolio_value": risk_metrics.portfolio_value,
            "total_exposure": risk_metrics.total_exposure,
            "var_95": risk_metrics.var_95,
            "max_position_size": risk_metrics.max_position_size,
            "leverage_used": risk_metrics.leverage_used,
            "margin_level": risk_metrics.margin_level,
            "last_update": risk_metrics.last_update
        }
    return {"error": "Risk metrics not available"}

@router.post("/market-data/update")
async def update_market_data(symbol: str, last_price: float, volume: float, bid: float, ask: float):
    """更新市场数据"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    _trading_monitor.update_market_data(symbol, last_price, volume, bid, ask)
    return {"status": "success", "message": "Market data updated"}

@router.post("/risk/update")
async def update_risk_metrics(portfolio_value: float, total_exposure: float, var_95: float, 
                          max_position_size: float, leverage_used: float, margin_level: float):
    """更新风险指标"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    from ..monitoring.trading_monitor import RiskMetrics
    import time
    
    risk_metrics = RiskMetrics(
        portfolio_value=portfolio_value,
        total_exposure=total_exposure,
        var_95=var_95,
        max_position_size=max_position_size,
        leverage_used=leverage_used,
        margin_level=margin_level,
        last_update=time.time()
    )
    
    _trading_monitor.update_risk_metrics(risk_metrics)
    return {"status": "success", "message": "Risk metrics updated"}

@router.post("/strategy/update")
async def update_strategy_performance(strategy_name: str, total_trades: int, win_trades: int, 
                                   loss_trades: int, win_rate: float, total_pnl: float, 
                                   max_drawdown: float, sharpe_ratio: float):
    """更新策略性能"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    from ..monitoring.trading_monitor import StrategyPerformance
    import time
    
    performance = StrategyPerformance(
        strategy_name=strategy_name,
        total_trades=total_trades,
        win_trades=win_trades,
        loss_trades=loss_trades,
        win_rate=win_rate,
        total_pnl=total_pnl,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        last_update=time.time()
    )
    
    _trading_monitor.update_strategy_performance(strategy_name, performance)
    return {"status": "success", "message": "Strategy performance updated"}