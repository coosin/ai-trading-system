"""
自动化交易规则配置

定义AI交易系统的自动化行为规则
"""

AUTOMATION_RULES = {
    "enabled": True,
    "version": "1.0.0",
    
    "market_monitoring": {
        "enabled": True,
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
        "intervals": {
            "high_volatility": 30,
            "normal": 60,
            "low_volatility": 120
        },
        "volatility_threshold": {
            "high": 0.03,
            "low": 0.01
        },
        "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
        "auto_adjust": True
    },
    
    "auto_trading": {
        "enabled": True,
        "max_positions": 5,
        "position_sizing": {
            "method": "dynamic",
            "base_risk": 0.02,
            "max_risk": 0.05,
            "adjust_by_confidence": True
        },
        "entry_rules": {
            "min_confidence": 0.65,
            "min_risk_reward": 1.5,
            "require_trend_alignment": True,
            "require_volume_confirmation": True
        },
        "exit_rules": {
            "stop_loss_type": "dynamic",
            "take_profit_type": "trailing",
            "trailing_stop_trigger": 0.02,
            "trailing_stop_distance": 0.01
        }
    },
    
    "risk_management": {
        "max_total_loss": 0.50,
        "max_daily_loss": 0.10,
        "max_position_loss": 0.05,
        "margin_ratio_warning": 0.50,
        "margin_ratio_critical": 0.80,
        "auto_reduce_on_warning": True,
        "extreme_market_pause": {
            "enabled": True,
            "volatility_spike_threshold": 0.05,
            "pause_duration_minutes": [60, 120, 180]
        }
    },
    
    "strategy_optimization": {
        "enabled": True,
        "optimization_interval": 3600,
        "min_trades_for_optimization": 10,
        "performance_window_days": 30,
        "auto_adjust_parameters": {
            "min_confidence": {"min": 0.5, "max": 0.85, "step": 0.05},
            "position_size": {"min": 0.01, "max": 0.10, "step": 0.01},
            "stop_loss_percent": {"min": 0.01, "max": 0.05, "step": 0.005}
        },
        "learning_rate": 0.1,
        "save_optimization_history": True
    },
    
    "strategy_development": {
        "enabled": True,
        "auto_discover_patterns": True,
        "backtest_new_strategies": True,
        "min_backtest_trades": 100,
        "min_win_rate": 0.55,
        "min_profit_factor": 1.2,
        "paper_trading_duration_hours": 24,
        "strategies": {
            "trend_following": {
                "enabled": True,
                "indicators": ["MA", "EMA", "MACD"],
                "timeframes": ["1h", "4h"]
            },
            "mean_reversion": {
                "enabled": True,
                "indicators": ["RSI", "Bollinger", "Stochastic"],
                "timeframes": ["15m", "1h"]
            },
            "breakout": {
                "enabled": True,
                "indicators": ["ATR", "Volume", "Bollinger"],
                "timeframes": ["5m", "15m", "1h"]
            },
            "scalping": {
                "enabled": True,
                "indicators": ["EMA", "Volume", "OrderBook"],
                "timeframes": ["1m", "5m"]
            }
        }
    },
    
    "market_analysis": {
        "auto_generate_reports": True,
        "report_intervals": {
            "hourly": True,
            "daily": True,
            "weekly": True
        },
        "save_to_memory": True,
        "indicators": {
            "trend": ["MA5", "MA20", "MA50", "EMA12", "EMA26"],
            "momentum": ["RSI", "MACD", "Stochastic"],
            "volatility": ["Bollinger", "ATR"],
            "volume": ["OBV", "Volume_MA"]
        }
    },
    
    "memory_management": {
        "auto_save_trades": True,
        "auto_save_optimizations": True,
        "auto_save_insights": True,
        "garbage_filter_enabled": True,
        "max_short_term_memory": 50,
        "max_long_term_memory": 500
    },
    
    "notifications": {
        "trade_executed": True,
        "position_opened": True,
        "position_closed": True,
        "risk_warning": True,
        "strategy_optimized": True,
        "new_strategy_discovered": True,
        "extreme_market": True
    }
}


def get_rule(path: str, default=None):
    """
    获取规则配置
    
    Args:
        path: 配置路径，如 "market_monitoring.intervals.normal"
        default: 默认值
        
    Returns:
        配置值
    """
    keys = path.split(".")
    value = AUTOMATION_RULES
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


def update_rule(path: str, value: Any) -> bool:
    """
    更新规则配置
    
    Args:
        path: 配置路径
        value: 新值
        
    Returns:
        是否成功
    """
    keys = path.split(".")
    config = AUTOMATION_RULES
    
    for key in keys[:-1]:
        if key not in config:
            return False
        config = config[key]
    
    config[keys[-1]] = value
    return True
