from types import SimpleNamespace

from src.modules.strategy.service import StrategyDomainService


def test_strategy_list_marks_manual_approval_items_as_pending():
    cfg = SimpleNamespace(
        to_dict=lambda: {
            "strategy_id": "dsl_btc_guarded",
            "name": "Guarded Research Strategy",
            "description": "research output",
            "strategy_type": "moving_average",
            "enabled": False,
            "symbols": ["BTC/USDT"],
            "timeframe": "1h",
            "parameters": {},
            "metadata": {
                "approval": {
                    "required": True,
                    "state": "manual_approval_required",
                    "approved": False,
                },
                "review_window": {"visible": True, "status": "pending_approval", "mode": "pre_publish_approval"},
            },
        }
    )
    manager = SimpleNamespace(strategy_configs={"dsl_btc_guarded": cfg}, performance_metrics={})

    items = StrategyDomainService(SimpleNamespace(strategy_manager=manager)).list_items()

    assert len(items) == 1
    assert items[0]["status"] == "pending_approval"
    assert items[0]["enabled"] is False
    assert items[0]["human_review_window"]["visible"] is True
