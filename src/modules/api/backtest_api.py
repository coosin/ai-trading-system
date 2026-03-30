"""
回测系统API接口

提供策略回测相关的API端点
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Query

from ..backtesting.backtest_engine import BacktestEngine, BacktestConfig
from ..backtesting.strategies.moving_average import MovingAverageStrategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])

# 策略映射
STRATEGIES = {
    "moving_average": MovingAverageStrategy
}

@router.post("/run")
async def run_backtest(
    symbol: str = Query(..., description="交易对"),
    strategy: str = Query(..., description="策略名称"),
    start_time: str = Query(..., description="开始时间 (YYYY-MM-DD HH:MM:SS)"),
    end_time: str = Query(..., description="结束时间 (YYYY-MM-DD HH:MM:SS)"),
    initial_balance: float = Query(..., description="初始资金"),
    time_frame: str = Query("1m", description="时间周期"),
    strategy_params: Dict[str, Any] = None
):
    """运行策略回测"""
    try:
        # 解析时间
        start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        
        # 验证策略
        if strategy not in STRATEGIES:
            raise HTTPException(status_code=400, detail=f"不支持的策略: {strategy}")
        
        # 创建策略实例
        strategy_class = STRATEGIES[strategy]
        strategy_config = strategy_params or {}
        strategy_config["name"] = strategy
        strategy_instance = strategy_class(strategy_config)
        
        # 创建回测配置
        config = BacktestConfig(
            symbol=symbol,
            start_time=start,
            end_time=end,
            initial_balance=initial_balance,
            time_frame=time_frame
        )
        
        # 初始化回测引擎
        engine = BacktestEngine()
        
        # 加载历史数据
        data = await engine.load_historical_data(
            symbol=symbol,
            start_time=start,
            end_time=end,
            time_frame=time_frame
        )
        
        # 运行回测
        result = await engine.run_backtest(strategy_instance, data, config)
        
        # 生成报告
        report = engine.generate_report(result)
        
        # 转换回测结果为可序列化格式
        trades = []
        for trade in result.trades:
            trades.append({
                "timestamp": trade.timestamp.isoformat(),
                "symbol": trade.symbol,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": trade.price,
                "fee": trade.fee,
                "balance": trade.balance,
                "position": trade.position,
                "pnl": trade.pnl,
                "cumulative_pnl": trade.cumulative_pnl
            })
        
        equity_curve = [(t.isoformat(), b) for t, b in result.equity_curve]
        drawdown_curve = [(t.isoformat(), d) for t, d in result.drawdown_curve]
        
        return {
            "report": report,
            "trades": trades,
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
            "statistics": {
                "final_balance": result.final_balance,
                "total_pnl": result.total_pnl,
                "win_rate": result.win_rate,
                "max_drawdown": result.max_drawdown,
                "sharpe_ratio": result.sharpe_ratio,
                "total_trades": result.total_trades
            }
        }
        
    except Exception as e:
        logger.error(f"回测失败: {e}")
        raise HTTPException(status_code=500, detail=f"回测失败: {str(e)}")

@router.get("/strategies")
async def get_available_strategies():
    """获取可用的策略列表"""
    strategies = []
    for name in STRATEGIES:
        strategies.append({
            "name": name,
            "description": get_strategy_description(name)
        })
    return {"strategies": strategies}

def get_strategy_description(strategy_name: str) -> str:
    """获取策略描述"""
    descriptions = {
        "moving_average": "移动平均线策略 - 当短期均线上穿长期均线时买入，下穿时卖出"
    }
    return descriptions.get(strategy_name, "")

@router.post("/optimize")
async def optimize_strategy(
    symbol: str = Query(..., description="交易对"),
    strategy: str = Query(..., description="策略名称"),
    start_time: str = Query(..., description="开始时间 (YYYY-MM-DD HH:MM:SS)"),
    end_time: str = Query(..., description="结束时间 (YYYY-MM-DD HH:MM:SS)"),
    initial_balance: float = Query(..., description="初始资金"),
    time_frame: str = Query("1m", description="时间周期"),
    parameter_ranges: Dict[str, List[Any]] = None
):
    """优化策略参数"""
    try:
        # 解析时间
        start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        
        # 验证策略
        if strategy not in STRATEGIES:
            raise HTTPException(status_code=400, detail=f"不支持的策略: {strategy}")
        
        # 加载历史数据
        engine = BacktestEngine()
        data = await engine.load_historical_data(
            symbol=symbol,
            start_time=start,
            end_time=end,
            time_frame=time_frame
        )
        
        # 定义参数范围（默认值）
        if strategy == "moving_average":
            short_windows = parameter_ranges.get("short_window", [10, 20, 30])
            long_windows = parameter_ranges.get("long_window", [50, 100, 150])
        else:
            raise HTTPException(status_code=400, detail="该策略不支持参数优化")
        
        # 遍历参数组合
        best_result = None
        best_params = None
        best_sharpe = -float('inf')
        
        for short in short_windows:
            for long in long_windows:
                if short >= long:
                    continue
                
                # 创建策略实例
                strategy_config = {
                    "name": strategy,
                    "short_window": short,
                    "long_window": long
                }
                strategy_instance = STRATEGIES[strategy](strategy_config)
                
                # 创建回测配置
                config = BacktestConfig(
                    symbol=symbol,
                    start_time=start,
                    end_time=end,
                    initial_balance=initial_balance,
                    time_frame=time_frame
                )
                
                # 运行回测
                result = await engine.run_backtest(strategy_instance, data, config)
                
                # 评估结果
                if result.sharpe_ratio > best_sharpe:
                    best_sharpe = result.sharpe_ratio
                    best_result = result
                    best_params = {"short_window": short, "long_window": long}
        
        if best_result:
            report = engine.generate_report(best_result)
            return {
                "best_params": best_params,
                "best_sharpe": best_sharpe,
                "report": report
            }
        else:
            raise HTTPException(status_code=400, detail="没有找到合适的参数组合")
        
    except Exception as e:
        logger.error(f"策略优化失败: {e}")
        raise HTTPException(status_code=500, detail=f"策略优化失败: {str(e)}")