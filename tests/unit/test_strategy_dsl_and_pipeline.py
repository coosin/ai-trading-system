import pandas as pd
import pytest


from src.modules.strategies.strategy_dsl import validate_dsl, bump_version
from src.modules.backtesting.strategies.dsl_strategy import DSLStrategy
from src.modules.backtesting.backtest_engine import BacktestEngine, BacktestConfig


def _sample_df(n: int = 200) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    close = pd.Series(range(n), index=idx).astype(float) + 100.0
    df = pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1.0,
        },
        index=idx,
    )
    return df


def test_validate_and_bump_version():
    dsl = {
        "name": "MA10x30",
        "version": "1.0.0",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "entry": [{"type": "ma_crossover", "params": {"fast": 10, "slow": 30}}],
        "exit": [{"type": "bollinger_reversion", "params": {"window": 20, "std": 2.0}}],
        "risk": {"stop_loss_pct": 0.02, "take_profit_pct": 0.04},
    }
    validate_dsl(dsl)
    assert bump_version("1.0.0") == "1.0.1"


@pytest.mark.asyncio
async def test_dsl_strategy_backtest_smoke():
    df = _sample_df(240)
    dsl = {
        "name": "MA12x40",
        "version": "1.0.0",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "entry": [{"type": "ma_crossover", "params": {"fast": 12, "slow": 40}}],
        "filters": [],
        "exit": [{"type": "bollinger_reversion", "params": {"window": 20, "std": 2.0}}],
        "risk": {"stop_loss_pct": 0.02, "take_profit_pct": 0.04},
    }

    engine = BacktestEngine()
    cfg = BacktestConfig(
        symbol="BTC/USDT",
        start_time=df.index[0].to_pydatetime(),
        end_time=df.index[-1].to_pydatetime(),
        initial_balance=10000.0,
        time_frame="1h",
    )
    strat = DSLStrategy({"name": "dsl", "dsl": dsl})
    res = await engine.run_backtest(strat, df.copy(), cfg)
    assert res.final_balance > 0
    assert res.total_trades >= 0

