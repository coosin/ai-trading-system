"""
监控系统API接口

提供交易监控相关的API端点
"""

import logging
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Query

from ..monitoring.trading_monitor import TradingMonitor, TradingAlert, TradeExecution, StrategyPerformance, MarketDataStatus, RiskMetrics
from ..intelligence.anomaly_detection import AnomalyDetector, AnomalyDetectionConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])

# 全局监控器实例
_trading_monitor = None
_anomaly_detector = None

def set_trading_monitor(monitor: TradingMonitor):
    """设置交易监控器实例"""
    global _trading_monitor
    _trading_monitor = monitor

def set_anomaly_detector(detector: AnomalyDetector):
    """设置异常检测器实例"""
    global _anomaly_detector
    _anomaly_detector = detector

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
            "last_update": perf.last_update,
            # 新增细粒度指标
            "avg_win": perf.avg_win,
            "avg_loss": perf.avg_loss,
            "profit_factor": perf.profit_factor,
            "expectancy": perf.expectancy,
            "drawdown_duration": perf.drawdown_duration,
            "current_drawdown": perf.current_drawdown,
            "win_streak": perf.win_streak,
            "loss_streak": perf.loss_streak,
            "best_trade": perf.best_trade,
            "worst_trade": perf.worst_trade,
            "avg_holding_period": perf.avg_holding_period
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
            "data_age": data.data_age,
            # 新增市场异常检测指标
            "price_change_24h": data.price_change_24h,
            "volume_change_24h": data.volume_change_24h,
            "volatility_24h": data.volatility_24h,
            "price_momentum": data.price_momentum,
            "volume_momentum": data.volume_momentum,
            "order_book_depth": data.order_book_depth,
            "liquidity_score": data.liquidity_score,
            "market_regime": data.market_regime,
            "anomaly_score": data.anomaly_score
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
async def update_market_data(symbol: str, last_price: float, volume: float, bid: float, ask: float, 
                            price_change_24h: float = 0.0, volume_change_24h: float = 0.0, 
                            volatility_24h: float = 0.0, price_momentum: float = 0.0, 
                            volume_momentum: float = 0.0, order_book_depth: float = 0.0, 
                            liquidity_score: float = 0.0, market_regime: str = "normal", 
                            anomaly_score: float = 0.0):
    """更新市场数据"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    _trading_monitor.update_market_data(symbol, last_price, volume, bid, ask, 
                                       price_change_24h, volume_change_24h, 
                                       volatility_24h, price_momentum, 
                                       volume_momentum, order_book_depth, 
                                       liquidity_score, market_regime, 
                                       anomaly_score)
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

# 异常检测相关端点

@router.get("/anomalies")
async def get_anomaly_events(limit: int = Query(50, description="返回的异常事件数量")):
    """获取异常事件"""
    if not _anomaly_detector:
        raise HTTPException(status_code=503, detail="Anomaly detection system not initialized")
    
    events = _anomaly_detector.get_anomaly_events(limit)
    return [{"event_id": event.event_id, "timestamp": event.timestamp, "severity": event.severity, "event_type": event.event_type, "message": event.message, "confidence": event.confidence, "details": event.details, "resolved": event.resolved} for event in events]

@router.get("/anomalies/active")
async def get_active_anomalies():
    """获取活跃异常"""
    if not _anomaly_detector:
        raise HTTPException(status_code=503, detail="Anomaly detection system not initialized")
    
    events = _anomaly_detector.get_active_anomalies()
    return [{"event_id": event.event_id, "timestamp": event.timestamp, "severity": event.severity, "event_type": event.event_type, "message": event.message, "confidence": event.confidence, "details": event.details} for event in events]

@router.post("/anomalies/{event_id}/resolve")
async def resolve_anomaly(event_id: str):
    """解决异常"""
    if not _anomaly_detector:
        raise HTTPException(status_code=503, detail="Anomaly detection system not initialized")
    
    _anomaly_detector.resolve_anomaly(event_id)
    return {"status": "success", "message": "Anomaly resolved"}

@router.get("/anomalies/model/performance")
async def get_model_performance():
    """获取模型性能"""
    if not _anomaly_detector:
        raise HTTPException(status_code=503, detail="Anomaly detection system not initialized")
    
    return _anomaly_detector.get_model_performance()

@router.post("/anomalies/data")
async def add_anomaly_data(data: Dict[str, float]):
    """添加异常检测数据点"""
    if not _anomaly_detector:
        raise HTTPException(status_code=503, detail="Anomaly detection system not initialized")
    
    _anomaly_detector.add_data_point(data)
    # 检测异常
    score = _anomaly_detector.detect_anomaly(data)
    return {"score": score.score, "is_anomaly": score.is_anomaly, "details": score.anomaly_details}