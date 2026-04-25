"""
监控系统API接口

提供交易监控相关的API端点
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..monitoring.trading_monitor import TradingMonitor, TradingAlert, TradeExecution, StrategyPerformance, MarketDataStatus, RiskMetrics
from ..intelligence.anomaly_detection import AnomalyDetector, AnomalyDetectionConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])

# 全局监控器实例
_trading_monitor = None
_enhanced_monitoring = None
_anomaly_detector = None

def set_trading_monitor(monitor: TradingMonitor):
    """设置交易监控器实例"""
    global _trading_monitor
    _trading_monitor = monitor


def set_enhanced_monitoring(monitor: Optional[Any]) -> None:
    """注册 MainController 的 EnhancedMonitoringSystem，供 /alerts 与摘要合并展示。"""
    global _enhanced_monitoring
    _enhanced_monitoring = monitor


def _serialize_trading_alert(alert: TradingAlert) -> Dict[str, Any]:
    return {
        "alert_id": alert.alert_id,
        "timestamp": float(alert.timestamp),
        "timestamp_iso": datetime.fromtimestamp(float(alert.timestamp)).isoformat(),
        "severity": alert.severity.value,
        "alert_type": alert.alert_type,
        "message": alert.message,
        "details": alert.details,
        "resolved": alert.resolved,
        "source": "trading_monitor",
    }


def _serialize_enhanced_alert(alert: Any) -> Dict[str, Any]:
    ts = alert.timestamp
    if isinstance(ts, datetime):
        ts_unix = ts.timestamp()
        ts_iso = ts.isoformat()
    else:
        ts_unix = float(ts)
        ts_iso = None
    rule = alert.rule
    return {
        "alert_id": alert.alert_id,
        "timestamp": ts_unix,
        "timestamp_iso": ts_iso,
        "severity": alert.level.value,
        "alert_type": getattr(rule, "rule_id", "") or getattr(rule, "name", ""),
        "message": alert.message,
        "details": {
            "metric": rule.metric,
            "value": alert.metric_value,
            "rule_name": rule.name,
            "threshold": rule.threshold,
            "condition": rule.condition,
        },
        "resolved": alert.resolved,
        "source": "enhanced_monitoring",
    }


def set_anomaly_detector(detector: AnomalyDetector):
    """设置异常检测器实例"""
    global _anomaly_detector
    _anomaly_detector = detector

@router.get("/summary")
async def get_monitoring_summary():
    """获取监控摘要"""
    if not _trading_monitor:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    out = dict(_trading_monitor.get_monitoring_summary())
    out["sources"] = {
        "trading_monitor": True,
        "enhanced_monitoring": _enhanced_monitoring is not None,
    }
    if _enhanced_monitoring:
        try:
            out["enhanced_monitoring"] = await _enhanced_monitoring.get_system_status()
        except Exception as e:
            logger.debug("enhanced_monitoring.get_system_status failed: %s", e)
            out["enhanced_monitoring"] = {"status": "error", "error": str(e)}
    return out

@router.get("/alerts")
async def get_active_alerts():
    """获取活跃告警（合并 TradingMonitor 与 EnhancedMonitoringSystem）"""
    if not _trading_monitor and not _enhanced_monitoring:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    rows: List[Dict[str, Any]] = []
    if _trading_monitor:
        for alert in _trading_monitor.get_active_alerts():
            rows.append(_serialize_trading_alert(alert))
    if _enhanced_monitoring:
        try:
            for alert in await _enhanced_monitoring.get_active_alerts():
                rows.append(_serialize_enhanced_alert(alert))
        except Exception as e:
            logger.warning("get_active_alerts enhanced: %s", e)
    rows.sort(key=lambda r: float(r.get("timestamp") or 0.0), reverse=True)
    return rows

@router.get("/alerts/history")
async def get_alert_history(limit: int = Query(50, description="返回的历史记录数量")):
    """获取告警历史（两路监控合并后按时间倒序截取）"""
    if not _trading_monitor and not _enhanced_monitoring:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")

    rows: List[Dict[str, Any]] = []
    if _trading_monitor:
        for alert in _trading_monitor.get_alert_history(limit):
            rows.append(_serialize_trading_alert(alert))
    if _enhanced_monitoring:
        try:
            hist = sorted(
                _enhanced_monitoring.alerts,
                key=lambda a: a.timestamp.timestamp() if isinstance(a.timestamp, datetime) else float(a.timestamp),
                reverse=True,
            )[:limit]
            for alert in hist:
                rows.append(_serialize_enhanced_alert(alert))
        except Exception as e:
            logger.warning("get_alert_history enhanced: %s", e)
    rows.sort(key=lambda r: float(r.get("timestamp") or 0.0), reverse=True)
    return rows[:limit]

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """解决告警（先在 TradingMonitor 中查找，再尝试 EnhancedMonitoringSystem）"""
    if not _trading_monitor and not _enhanced_monitoring:
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")

    resolved = False
    if _trading_monitor:
        active_ids = {a.alert_id for a in _trading_monitor.get_active_alerts()}
        if alert_id in active_ids:
            _trading_monitor.resolve_alert(alert_id)
            resolved = True
    if not resolved and _enhanced_monitoring:
        resolved = await _enhanced_monitoring.resolve_alert(alert_id)
    if not resolved:
        raise HTTPException(status_code=404, detail="Alert not found")
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
            "last_update": risk_metrics.last_update,
            "source": "trading_monitor",
        }
    # Fallback: keep endpoint usable for dashboards even when no live risk sample
    return {
        "portfolio_value": 0.0,
        "total_exposure": 0.0,
        "var_95": 0.0,
        "max_position_size": 0.0,
        "leverage_used": 0.0,
        "margin_level": 0.0,
        "risk_level": "unknown",
        "position_count": 0,
        "warnings": [],
        "source": "fallback:empty",
    }

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

# 主动性AI系统相关端点

_proactive_ai = None

def set_proactive_ai(proactive_ai):
    """设置主动性AI系统实例"""
    global _proactive_ai
    _proactive_ai = proactive_ai

@router.post("/proactive-ai/start")
async def start_proactive_ai():
    """启动主动性AI系统（用于启动链路阻塞后的手动恢复）"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    try:
        await _proactive_ai.start()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"start_failed:{type(e).__name__}:{e}")
    return {"ok": True, "status": "started"}

@router.post("/proactive-ai/stop")
async def stop_proactive_ai():
    """停止主动性AI系统"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    try:
        await _proactive_ai.stop()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stop_failed:{type(e).__name__}:{e}")
    return {"ok": True, "status": "stopped"}

@router.get("/proactive-ai/status")
async def get_proactive_ai_status():
    """获取主动性AI系统状态"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    
    return _proactive_ai.get_status()

@router.get("/proactive-ai/opportunities")
async def get_proactive_opportunities():
    """获取当前交易机会"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    
    opportunities = _proactive_ai.market_scanner.get_opportunities()
    return [{
        "symbol": opp.symbol,
        "type": opp.opportunity_type.value,
        "direction": opp.direction,
        "confidence": opp.confidence,
        "entry_price": opp.entry_price,
        "stop_loss": opp.stop_loss,
        "take_profit": opp.take_profit,
        "reasoning": opp.reasoning,
        "priority": opp.priority,
        "timestamp": opp.timestamp.isoformat() if opp.timestamp else None,
        "expires_at": opp.expires_at.isoformat() if opp.expires_at else None
    } for opp in opportunities]

@router.get("/proactive-ai/insights")
async def get_proactive_insights():
    """获取市场洞察"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    
    insights = _proactive_ai.market_scanner.get_insights()
    result = {}
    for symbol, insight in insights.items():
        result[symbol] = {
            "trend": insight.trend,
            "trend_strength": insight.trend_strength,
            "volatility": insight.volatility,
            "volume_profile": insight.volume_profile,
            "support_levels": insight.support_levels,
            "resistance_levels": insight.resistance_levels,
            "sentiment": insight.sentiment,
            "sentiment_score": insight.sentiment_score,
            "news_impact": insight.news_impact,
            "timestamp": insight.timestamp.isoformat() if insight.timestamp else None
        }
    return result

@router.get("/proactive-ai/market-state")
async def get_proactive_market_state():
    """获取市场状态"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    
    return _proactive_ai.market_scanner.get_market_state()

@router.get("/proactive-ai/news")
async def get_proactive_news():
    """获取最新新闻"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    
    news = _proactive_ai.info_collector.get_latest_news()
    return news

@router.get("/proactive-ai/sentiment")
async def get_proactive_sentiment():
    """获取社交情绪"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    
    return _proactive_ai.info_collector.get_social_sentiment()

@router.get("/proactive-ai/fear-greed")
async def get_fear_greed_index():
    """获取恐慌贪婪指数"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    
    index = _proactive_ai.info_collector.get_fear_greed_index()
    return {"fear_greed_index": index}

@router.get("/proactive-ai/best-strategy")
async def get_best_strategy():
    """获取最佳策略"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    
    return {
        "best_strategy": _proactive_ai.strategy_selector.get_best_strategy(),
        "strategy_scores": _proactive_ai.strategy_selector.get_strategy_scores()
    }

@router.get("/proactive-ai/stats")
async def get_proactive_stats():
    """获取主动性AI统计信息"""
    if not _proactive_ai:
        raise HTTPException(status_code=503, detail="Proactive AI system not initialized")
    
    return _proactive_ai.market_scanner.get_stats()