"""
Strategy research pipeline:
- generate candidates (DSL primitives combos)
- backtest on train window
- optimize parameters (simple grid)
- walk-forward evaluate on test window
- gate by risk metrics (drawdown, sharpe, trades)
- publish into StrategyManager as StrategyConfig with versioned metadata
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.modules.backtesting.backtest_engine import BacktestConfig, BacktestEngine
from src.modules.backtesting.strategies.dsl_strategy import DSLStrategy
from src.modules.strategies.strategy_dsl import bump_version, normalize_symbol, validate_dsl

logger = logging.getLogger(__name__)


@dataclass
class ResearchGates:
    min_sharpe: float = 0.8
    max_drawdown: float = 0.25
    min_trades: int = 8


class StrategyResearchPipeline:
    def __init__(self, main_controller=None, gates: Optional[ResearchGates] = None):
        self.main_controller = main_controller
        self.gates = gates or ResearchGates()
        self.engine = BacktestEngine()

    async def run_cycle(self, symbols: List[str], timeframe: str = "1h", lookback_days: int = 30) -> Dict[str, Any]:
        results: Dict[str, Any] = {"published": [], "rejected": [], "errors": []}
        for sym in symbols:
            try:
                published = await self._research_symbol(sym, timeframe=timeframe, lookback_days=lookback_days)
                results["published"].extend(published)
            except Exception as e:
                logger.error(f"research cycle failed for {sym}: {e}")
                results["errors"].append({"symbol": sym, "error": str(e)})
        return results

    async def _research_symbol(self, symbol: str, timeframe: str, lookback_days: int) -> List[Dict[str, Any]]:
        exchange = getattr(getattr(self.main_controller, "ai_trading_engine", None), "exchange", None)
        if not exchange:
            return []
        end = datetime.now()
        start = end - timedelta(days=lookback_days)
        df = await self._load_klines_df(exchange, symbol, timeframe=timeframe, limit=720)
        if df is None or len(df) < 120:
            return []

        train_df, test_df = self._walk_forward_split(df, train_ratio=0.7)
        candidates = self._generate_candidates(symbol, timeframe)

        published: List[Dict[str, Any]] = []
        for dsl in candidates:
            validate_dsl(dsl)
            best_dsl, train_metrics = await self._optimize_candidate(dsl, train_df)
            test_metrics = await self._backtest(best_dsl, test_df)

            if self._passes_gates(test_metrics):
                item = await self._publish(best_dsl, test_metrics, train_metrics)
                if item:
                    published.append(item)
        return published

    async def _load_klines_df(self, exchange, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        tf = timeframe.lower().replace("h", "H").replace("m", "m")
        raw = await exchange.get_klines(symbol.replace("/", "-"), tf, limit=limit)
        if not raw:
            return None
        rows = []
        for k in raw:
            if isinstance(k, (list, tuple)) and len(k) >= 6:
                ts, o, h, l, c, v = k[:6]
            elif isinstance(k, dict):
                ts = k.get("ts") or k.get("timestamp") or k.get("t")
                o, h, l, c, v = k.get("open"), k.get("high"), k.get("low"), k.get("close"), k.get("volume")
            else:
                continue
            try:
                rows.append(
                    {
                        "timestamp": pd.to_datetime(ts, unit="ms", errors="coerce"),
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                        "volume": float(v),
                    }
                )
            except Exception:
                continue
        df = pd.DataFrame(rows).dropna()
        if df.empty:
            return None
        df = df.sort_values("timestamp").set_index("timestamp")
        return df

    def _walk_forward_split(self, df: pd.DataFrame, train_ratio: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
        n = len(df)
        cut = max(50, int(n * train_ratio))
        return df.iloc[:cut].copy(), df.iloc[cut:].copy()

    def _generate_candidates(self, symbol: str, timeframe: str) -> List[Dict[str, Any]]:
        symbol = normalize_symbol(symbol)
        base = {
            "symbol": symbol,
            "timeframe": timeframe,
            "risk": {"stop_loss_pct": 0.02, "take_profit_pct": 0.04},
        }
        candidates: List[Dict[str, Any]] = []
        for fast in (10, 12, 16, 20):
            for slow in (30, 40, 50, 60):
                if fast >= slow:
                    continue
                candidates.append(
                    {
                        **base,
                        "name": f"MA{fast}x{slow}",
                        "version": "1.0.0",
                        "entry": [{"type": "ma_crossover", "params": {"fast": fast, "slow": slow}}],
                        "filters": [],
                        "exit": [{"type": "bollinger_reversion", "params": {"window": 20, "std": 2.0}}],
                        "tags": ["dsl", "ma", "walkforward"],
                        "metadata": {"generator": "grid"},
                    }
                )
        # breakout variants
        for lookback in (12, 20, 30):
            candidates.append(
                {
                    **base,
                    "name": f"Breakout{lookback}",
                    "version": "1.0.0",
                    "entry": [{"type": "breakout_channel", "params": {"lookback": lookback}}],
                    "filters": [],
                    "exit": [{"type": "bollinger_reversion", "params": {"window": 20, "std": 2.0}}],
                    "tags": ["dsl", "breakout", "walkforward"],
                    "metadata": {"generator": "grid"},
                }
            )
        return candidates

    async def _optimize_candidate(self, dsl: Dict[str, Any], train_df: pd.DataFrame) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        # For MA candidates, optimize fast/slow around the initial values.
        entry = (dsl.get("entry") or [{}])[0]
        if entry.get("type") != "ma_crossover":
            metrics = await self._backtest(dsl, train_df)
            return dsl, metrics

        init_fast = int(entry.get("params", {}).get("fast", 20))
        init_slow = int(entry.get("params", {}).get("slow", 50))
        fast_space = sorted(set([max(6, init_fast - 4), init_fast, init_fast + 4, init_fast + 8]))
        slow_space = sorted(set([max(init_fast + 10, init_slow - 10), init_slow, init_slow + 10, init_slow + 20]))

        best_dsl = dsl
        best_metrics = {"sharpe_ratio": -1.0}
        for fast in fast_space:
            for slow in slow_space:
                if fast >= slow:
                    continue
                cand = {**dsl}
                cand["entry"] = [{"type": "ma_crossover", "params": {"fast": int(fast), "slow": int(slow)}}]
                metrics = await self._backtest(cand, train_df)
                if metrics.get("sharpe_ratio", -1) > best_metrics.get("sharpe_ratio", -1):
                    best_metrics = metrics
                    best_dsl = cand
        return best_dsl, best_metrics

    async def _backtest(self, dsl: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
        validate_dsl(dsl)
        config = BacktestConfig(
            symbol=dsl.get("symbol", "BTC/USDT"),
            start_time=df.index[0].to_pydatetime(),
            end_time=df.index[-1].to_pydatetime(),
            initial_balance=10000.0,
            time_frame=dsl.get("timeframe", "1h"),
        )
        strat = DSLStrategy({"name": dsl.get("name", "dsl"), "dsl": dsl})
        res = await self.engine.run_backtest(strat, df.copy(), config)
        return {
            "final_balance": res.final_balance,
            "total_pnl": res.total_pnl,
            "win_rate": float(res.win_rate) / 100.0 if res.win_rate > 1 else float(res.win_rate),
            "max_drawdown": float(res.max_drawdown) / 100.0 if res.max_drawdown > 1 else float(res.max_drawdown),
            "sharpe_ratio": float(res.sharpe_ratio),
            "total_trades": int(res.total_trades),
        }

    def _passes_gates(self, metrics: Dict[str, Any]) -> bool:
        return (
            metrics.get("sharpe_ratio", 0) >= self.gates.min_sharpe
            and metrics.get("max_drawdown", 1) <= self.gates.max_drawdown
            and metrics.get("total_trades", 0) >= self.gates.min_trades
        )

    async def _publish(self, dsl: Dict[str, Any], test_metrics: Dict[str, Any], train_metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.main_controller or not getattr(self.main_controller, "strategy_manager", None):
            return None
        strategy_manager = self.main_controller.strategy_manager

        # Create StrategyConfig-like dict that StrategyManager.load_strategy_config understands
        strategy_id = f"dsl_{dsl['symbol'].replace('/','_')}_{dsl['name'].replace(' ','_')}"
        version = bump_version(dsl.get("version", "1.0.0"))
        dsl = {**dsl, "version": version}

        config_data = {
            "strategy_id": strategy_id,
            "name": dsl["name"],
            "description": f"DSL strategy auto-researched. gates={self.gates}",
            "strategy_type": "ai_driven",
            "enabled": True,
            "version": version,
            "parameters": {"dsl": dsl},
            "symbols": [dsl.get("symbol", "BTC/USDT")],
            "timeframe": dsl.get("timeframe", "1h"),
            "initial_capital": 10000.0,
            "metadata": {
                "dsl": dsl,
                "research": {
                    "train": train_metrics,
                    "test": test_metrics,
                    "gates": self.gates.__dict__,
                    "published_at": datetime.now().isoformat(),
                },
            },
        }

        cfg = await strategy_manager.load_strategy_config(config_data)
        if not cfg:
            return None

        # Audit + memory trace
        if hasattr(self.main_controller, "log_audit_event"):
            try:
                from src.modules.core.audit_logger import AuditEventType, AuditSeverity

                await self.main_controller.log_audit_event(
                    event_type=AuditEventType.STRATEGY_LOAD,
                    severity=AuditSeverity.INFO,
                    action="publish_researched_strategy",
                    details={"strategy_id": strategy_id, "version": version, "metrics": test_metrics},
                    source="research_pipeline",
                )
            except Exception:
                pass

        if hasattr(self.main_controller, "memory_gateway") and self.main_controller.memory_gateway:
            try:
                await self.main_controller.memory_gateway.add_memory(
                    memory_type="strategy",
                    content=f"发布策略 {strategy_id} v{version}: test={test_metrics}",
                    metadata={"strategy_id": strategy_id, "version": version, "dsl": dsl, "test": test_metrics},
                    source_module="strategy_research_pipeline",
                    importance=0.85,
                    tags=["strategy", "research", "walkforward"],
                )
            except Exception:
                pass

        return {"strategy_id": strategy_id, "version": version, "test": test_metrics}

