"""
策略自动优化器

自动分析交易表现，优化策略参数，开发新策略
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import statistics

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """策略类型"""
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    SCALPING = "scalping"
    GRID = "grid"
    CUSTOM = "custom"


@dataclass
class StrategyPerformance:
    """策略表现"""
    strategy_id: str
    strategy_type: StrategyType
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class OptimizationResult:
    """优化结果"""
    optimization_id: str
    strategy_id: str
    timestamp: datetime
    old_parameters: Dict[str, Any]
    new_parameters: Dict[str, Any]
    reason: str
    expected_improvement: str
    backtest_results: Optional[Dict] = None


@dataclass
class NewStrategyProposal:
    """新策略提案"""
    proposal_id: str
    strategy_type: StrategyType
    discovery_reason: str
    indicators: List[str]
    entry_rules: Dict[str, Any]
    exit_rules: Dict[str, Any]
    timeframes: List[str]
    backtest_results: Optional[Dict] = None
    paper_trading_results: Optional[Dict] = None
    status: str = "proposed"  # proposed, backtesting, paper_trading, approved, rejected


class StrategyOptimizer:
    """
    策略自动优化器
    
    功能：
    1. 自动分析策略表现
    2. 优化策略参数
    3. 发现新的交易模式
    4. 开发和测试新策略
    """
    
    def __init__(self, memory_manager=None, data_storage=None):
        self.memory_manager = memory_manager
        self.data_storage = data_storage
        
        self.strategy_performances: Dict[str, StrategyPerformance] = {}
        self.optimization_history: List[OptimizationResult] = []
        self.new_strategy_proposals: List[NewStrategyProposal] = []
        
        self.config = {
            "min_trades_for_analysis": 10,
            "optimization_interval": 3600,
            "backtest_min_trades": 100,
            "backtest_min_win_rate": 0.55,
            "backtest_min_profit_factor": 1.2,
            "paper_trading_hours": 24,
            "max_parameter_adjustment": 0.2
        }
        
        self._running = False
        self._optimization_task = None
        
        logger.info("策略优化器初始化完成")
    
    async def start(self) -> None:
        """启动优化器"""
        self._running = True
        self._optimization_task = asyncio.create_task(self._optimization_loop())
        logger.info("✅ 策略优化器已启动")
    
    async def stop(self) -> None:
        """停止优化器"""
        self._running = False
        if self._optimization_task:
            self._optimization_task.cancel()
        logger.info("策略优化器已停止")
    
    async def _optimization_loop(self) -> None:
        """优化循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config["optimization_interval"])
                
                logger.info("🔄 开始策略优化分析...")
                
                await self._analyze_all_strategies()
                
                await self._optimize_underperforming_strategies()
                
                await self._discover_new_patterns()
                
                await self._process_new_strategy_proposals()
                
                await self._save_optimization_results()
                
            except Exception as e:
                logger.error(f"优化循环错误: {e}")
                await asyncio.sleep(60)
    
    async def record_trade(self, trade: Dict[str, Any]) -> None:
        """记录交易用于分析"""
        strategy_id = trade.get("strategy_id", "default")
        
        if strategy_id not in self.strategy_performances:
            self.strategy_performances[strategy_id] = StrategyPerformance(
                strategy_id=strategy_id,
                strategy_type=StrategyType(trade.get("strategy_type", "custom"))
            )
        
        perf = self.strategy_performances[strategy_id]
        perf.total_trades += 1
        
        pnl = trade.get("pnl", 0)
        perf.total_pnl += pnl
        
        if pnl > 0:
            perf.winning_trades += 1
            perf.best_trade = max(perf.best_trade, pnl)
            perf.avg_win = (perf.avg_win * (perf.winning_trades - 1) + pnl) / perf.winning_trades
        else:
            perf.losing_trades += 1
            perf.worst_trade = min(perf.worst_trade, pnl)
            perf.avg_loss = (perf.avg_loss * (perf.losing_trades - 1) + pnl) / perf.losing_trades
        
        perf.win_rate = perf.winning_trades / perf.total_trades if perf.total_trades > 0 else 0
        
        if perf.avg_loss != 0:
            perf.profit_factor = abs(perf.avg_win / perf.avg_loss)
        
        perf.last_updated = datetime.now()
        
        if perf.total_trades >= self.config["min_trades_for_analysis"]:
            await self._check_and_optimize(strategy_id)
    
    async def _analyze_all_strategies(self) -> Dict[str, StrategyPerformance]:
        """分析所有策略表现"""
        analysis = {}
        
        for strategy_id, perf in self.strategy_performances.items():
            if perf.total_trades >= self.config["min_trades_for_analysis"]:
                analysis[strategy_id] = perf
                
                logger.info(f"📊 策略 {strategy_id}: "
                           f"交易={perf.total_trades}, "
                           f"胜率={perf.win_rate:.1%}, "
                           f"盈亏比={perf.profit_factor:.2f}, "
                           f"总盈亏={perf.total_pnl:+.2f}")
        
        return analysis
    
    async def _optimize_underperforming_strategies(self) -> List[OptimizationResult]:
        """优化表现不佳的策略"""
        optimizations = []
        
        for strategy_id, perf in self.strategy_performances.items():
            if perf.win_rate < 0.45 or perf.profit_factor < 1.0:
                optimization = await self._optimize_strategy(strategy_id, perf)
                if optimization:
                    optimizations.append(optimization)
        
        return optimizations
    
    async def _optimize_strategy(self, strategy_id: str, 
                                perf: StrategyPerformance) -> Optional[OptimizationResult]:
        """优化单个策略"""
        old_params = perf.parameters.copy()
        new_params = old_params.copy()
        reason = ""
        expected_improvement = ""
        
        if perf.win_rate < 0.45:
            if "min_confidence" in new_params:
                old_value = new_params.get("min_confidence", 0.65)
                new_params["min_confidence"] = min(0.85, old_value + 0.05)
                reason = f"胜率过低({perf.win_rate:.1%})，提高入场门槛"
                expected_improvement = "减少低质量信号，提高胜率"
        
        if perf.profit_factor < 1.0:
            if "stop_loss_percent" in new_params:
                old_value = new_params.get("stop_loss_percent", 0.02)
                new_params["stop_loss_percent"] = max(0.01, old_value - 0.005)
                reason = f"盈亏比过低({perf.profit_factor:.2f})，收紧止损"
                expected_improvement = "减少单笔亏损，改善盈亏比"
        
        if new_params == old_params:
            return None
        
        optimization = OptimizationResult(
            optimization_id=f"opt_{datetime.now().timestamp()}",
            strategy_id=strategy_id,
            timestamp=datetime.now(),
            old_parameters=old_params,
            new_parameters=new_params,
            reason=reason,
            expected_improvement=expected_improvement
        )
        
        self.optimization_history.append(optimization)
        perf.parameters = new_params
        
        if self.memory_manager:
            await self._save_optimization_to_memory(optimization)
        
        logger.info(f"🔧 策略优化: {strategy_id} - {reason}")
        
        return optimization
    
    async def _check_and_optimize(self, strategy_id: str) -> None:
        """检查并优化策略"""
        perf = self.strategy_performances.get(strategy_id)
        if not perf:
            return
        
        if perf.win_rate < 0.4 or perf.profit_factor < 0.8:
            await self._optimize_strategy(strategy_id, perf)
    
    async def _discover_new_patterns(self) -> List[NewStrategyProposal]:
        """发现新的交易模式"""
        proposals = []
        
        if not self.data_storage:
            return proposals
        
        try:
            for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
                klines = await self.data_storage.get_klines(symbol, "1h", limit=500)
                
                if not klines or len(klines) < 100:
                    continue
                
                patterns = self._analyze_patterns(klines)
                
                for pattern in patterns:
                    proposal = NewStrategyProposal(
                        proposal_id=f"prop_{datetime.now().timestamp()}",
                        strategy_type=pattern["type"],
                        discovery_reason=pattern["reason"],
                        indicators=pattern["indicators"],
                        entry_rules=pattern["entry_rules"],
                        exit_rules=pattern["exit_rules"],
                        timeframes=pattern["timeframes"]
                    )
                    proposals.append(proposal)
                    self.new_strategy_proposals.append(proposal)
                    
                    logger.info(f"💡 发现新模式: {pattern['type'].value} - {pattern['reason']}")
            
        except Exception as e:
            logger.error(f"发现新模式失败: {e}")
        
        return proposals
    
    def _analyze_patterns(self, klines: List[Dict]) -> List[Dict]:
        """分析K线数据发现模式"""
        patterns = []
        
        try:
            closes = [k.get("close", 0) for k in klines]
            volumes = [k.get("volume", 0) for k in klines]
            
            if len(closes) < 50:
                return patterns
            
            ma20 = sum(closes[-20:]) / 20
            ma50 = sum(closes[-50:]) / 50
            
            if ma20 > ma50 * 1.02:
                patterns.append({
                    "type": StrategyType.TREND_FOLLOWING,
                    "reason": "发现上升趋势模式",
                    "indicators": ["MA20", "MA50", "EMA"],
                    "entry_rules": {"condition": "MA20 > MA50", "confirmation": "price > MA20"},
                    "exit_rules": {"condition": "MA20 < MA50", "stop_loss": "MA50"},
                    "timeframes": ["1h", "4h"]
                })
            
            rsi = self._calculate_rsi(closes, 14)
            if rsi and rsi < 30:
                patterns.append({
                    "type": StrategyType.MEAN_REVERSION,
                    "reason": "发现超卖反弹模式",
                    "indicators": ["RSI", "Bollinger", "Stochastic"],
                    "entry_rules": {"condition": "RSI < 30", "confirmation": "price < bollinger_lower"},
                    "exit_rules": {"condition": "RSI > 70", "take_profit": "bollinger_middle"},
                    "timeframes": ["15m", "1h"]
                })
            
            if volumes:
                avg_volume = sum(volumes[-20:]) / 20
                recent_volume = volumes[-1]
                
                if recent_volume > avg_volume * 2:
                    patterns.append({
                        "type": StrategyType.BREAKOUT,
                        "reason": "发现放量突破模式",
                        "indicators": ["Volume", "ATR", "Bollinger"],
                        "entry_rules": {"condition": "volume > 2*avg", "confirmation": "price > bollinger_upper"},
                        "exit_rules": {"condition": "volume < avg", "stop_loss": "ATR*2"},
                        "timeframes": ["5m", "15m", "1h"]
                    })
            
        except Exception as e:
            logger.error(f"分析模式失败: {e}")
        
        return patterns
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """计算RSI"""
        if len(prices) < period + 1:
            return None
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    async def _process_new_strategy_proposals(self) -> None:
        """处理新策略提案"""
        for proposal in self.new_strategy_proposals:
            if proposal.status == "proposed":
                proposal.status = "backtesting"
                
                backtest_result = await self._backtest_strategy(proposal)
                proposal.backtest_results = backtest_result
                
                if backtest_result and self._is_backtest_valid(backtest_result):
                    proposal.status = "paper_trading"
                    logger.info(f"✅ 策略 {proposal.proposal_id} 回测通过，进入模拟测试")
                else:
                    proposal.status = "rejected"
                    logger.info(f"❌ 策略 {proposal.proposal_id} 回测未通过")
    
    async def _backtest_strategy(self, proposal: NewStrategyProposal) -> Optional[Dict]:
        """回测策略"""
        if not self.data_storage:
            return None
        
        try:
            total_trades = 0
            winning_trades = 0
            total_pnl = 0
            
            for symbol in ["BTC/USDT", "ETH/USDT"]:
                for tf in proposal.timeframes:
                    klines = await self.data_storage.get_klines(symbol, tf, limit=500)
                    
                    if not klines:
                        continue
                    
                    for i in range(50, len(klines) - 1):
                        signal = self._check_entry_signal(klines[:i], proposal)
                        
                        if signal:
                            entry_price = klines[i]["close"]
                            exit_price = klines[i+1]["close"]
                            
                            pnl = (exit_price - entry_price) / entry_price
                            total_trades += 1
                            total_pnl += pnl
                            
                            if pnl > 0:
                                winning_trades += 1
            
            if total_trades < self.config["backtest_min_trades"]:
                return None
            
            win_rate = winning_trades / total_trades
            profit_factor = abs(total_pnl / (total_trades - winning_trades)) if (total_trades - winning_trades) > 0 else 0
            
            return {
                "total_trades": total_trades,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "total_pnl": total_pnl
            }
            
        except Exception as e:
            logger.error(f"回测策略失败: {e}")
            return None
    
    def _check_entry_signal(self, klines: List[Dict], proposal: NewStrategyProposal) -> bool:
        """检查入场信号"""
        if len(klines) < 20:
            return False
        
        closes = [k.get("close", 0) for k in klines]
        entry_rules = proposal.entry_rules
        
        if "MA20 > MA50" in entry_rules.get("condition", ""):
            ma20 = sum(closes[-20:]) / 20
            ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20
            if ma20 <= ma50:
                return False
        
        if "RSI < 30" in entry_rules.get("condition", ""):
            rsi = self._calculate_rsi(closes)
            if not rsi or rsi >= 30:
                return False
        
        return True
    
    def _is_backtest_valid(self, result: Dict) -> bool:
        """检查回测结果是否有效"""
        return (
            result["win_rate"] >= self.config["backtest_min_win_rate"] and
            result["profit_factor"] >= self.config["backtest_min_profit_factor"]
        )
    
    async def _save_optimization_to_memory(self, optimization: OptimizationResult) -> None:
        """保存优化结果到记忆"""
        if not self.memory_manager:
            return
        
        try:
            content = f"策略优化 [{optimization.strategy_id}]: {optimization.reason}"
            
            if hasattr(self.memory_manager, 'enhanced_memory') and self.memory_manager.enhanced_memory:
                self.memory_manager.enhanced_memory.save_strategy_optimization(
                    strategy_name=optimization.strategy_id,
                    optimization_type="parameter",
                    old_params=optimization.old_parameters,
                    new_params=optimization.new_parameters,
                    reason=optimization.reason,
                    expected_improvement=optimization.expected_improvement
                )
            
        except Exception as e:
            logger.error(f"保存优化结果到记忆失败: {e}")
    
    async def _save_optimization_results(self) -> None:
        """保存优化结果"""
        if not self.data_storage:
            return
        
        try:
            results = {
                "timestamp": datetime.now().isoformat(),
                "strategies": {
                    sid: {
                        "total_trades": p.total_trades,
                        "win_rate": p.win_rate,
                        "profit_factor": p.profit_factor,
                        "total_pnl": p.total_pnl,
                        "parameters": p.parameters
                    }
                    for sid, p in self.strategy_performances.items()
                },
                "optimizations": len(self.optimization_history),
                "new_proposals": len(self.new_strategy_proposals)
            }
            
            results_path = Path("data/strategy_optimization.json")
            results_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存优化结果失败: {e}")
    
    def get_status(self) -> Dict:
        """获取优化器状态"""
        return {
            "running": self._running,
            "strategies_tracked": len(self.strategy_performances),
            "optimizations_performed": len(self.optimization_history),
            "new_proposals": len(self.new_strategy_proposals),
            "config": self.config
        }
    
    def get_strategy_performance(self, strategy_id: str) -> Optional[StrategyPerformance]:
        """获取策略表现"""
        return self.strategy_performances.get(strategy_id)
    
    def get_all_performances(self) -> Dict[str, StrategyPerformance]:
        """获取所有策略表现"""
        return self.strategy_performances.copy()
