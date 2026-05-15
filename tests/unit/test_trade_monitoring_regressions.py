from __future__ import annotations

from src.modules.api.monitoring_api import _average_holding_period_hours, _realized_trade_rows, _trade_series_metrics


def test_trade_series_metrics_computes_drawdown_sharpe_and_streaks():
    rows = [
        {"timestamp": "2025-01-01T00:00:00", "pnl": 10},
        {"timestamp": "2025-01-01T00:01:00", "pnl": -5},
        {"timestamp": "2025-01-01T00:02:00", "pnl": -3},
        {"timestamp": "2025-01-01T00:03:00", "pnl": 8},
        {"timestamp": "2025-01-01T00:04:00", "pnl": 6},
    ]

    stats = _trade_series_metrics(rows)

    assert stats["total_trades"] == 5
    assert stats["max_drawdown"] == 8.0
    assert stats["current_drawdown"] == 0.0
    assert stats["drawdown_duration"] == 2
    assert stats["win_streak"] == 2
    assert stats["loss_streak"] == 2
    assert stats["sharpe_ratio"] != 0.0
    assert stats["best_trade"] == 10.0
    assert stats["worst_trade"] == -5.0


def test_realized_trade_rows_and_holding_period_pair_open_close_legs():
    rows = [
        {
            "timestamp": "2025-01-01T00:00:00",
            "symbol": "BTC/USDT",
            "side": "buy",
            "status": "filled",
            "metadata": {"action": "open", "decision_action": "OPEN_LONG"},
        },
        {
            "timestamp": "2025-01-01T02:00:00",
            "symbol": "BTC/USDT",
            "side": "sell",
            "status": "filled",
            "pnl": 25,
            "metadata": {"action": "close", "decision_action": "CLOSE_LONG"},
        },
        {
            "timestamp": "2025-01-01T03:00:00",
            "symbol": "ETH/USDT",
            "side": "sell",
            "status": "filled",
            "metadata": {"action": "open", "decision_action": "OPEN_SHORT"},
        },
        {
            "timestamp": "2025-01-01T04:30:00",
            "symbol": "ETH/USDT",
            "side": "buy",
            "status": "filled",
            "pnl": -10,
            "metadata": {"action": "close", "decision_action": "CLOSE_SHORT"},
        },
    ]

    realized = _realized_trade_rows(rows)
    assert len(realized) == 2

    avg_holding = _average_holding_period_hours(rows)
    assert round(avg_holding, 2) == 1.75
