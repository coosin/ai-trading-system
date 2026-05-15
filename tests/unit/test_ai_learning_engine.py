from types import SimpleNamespace

import pytest

from src.modules.core.ai_learning_engine import AILearningEngine, LessonType, TradingLesson
from src.modules.core.decision_trace_store import DecisionTraceStore
from src.modules.core.strategy_manager import StrategyLifecycleStage, StrategyManager


class _FakeMemoryManager:
    def __init__(self):
        self.saved = []

    async def add_memory(self, *args, **kwargs):
        self.saved.append(("add_memory", args, kwargs))

    async def save_knowledge_document(self, *args, **kwargs):
        self.saved.append(("save_knowledge_document", args, kwargs))
        return "doc-id"


@pytest.mark.asyncio
async def test_generate_weekly_research_review_persists_document():
    mm = _FakeMemoryManager()
    engine = AILearningEngine(memory_manager=mm)
    engine.learning_reports = []
    engine.lessons = [
        TradingLesson(
            id="1",
            lesson_type=LessonType.SUCCESS_PATTERN,
            title="BTC success",
            content="ok",
            context={"strategy": "s1"},
            impact_score=0.8,
            confidence=0.9,
        )
    ]
    engine._self_review_summary = {"mistake_tags": ["low_confidence"], "lesson_summary": "summary"}
    engine._trace_feedback_summary = {
        "top_execution_failure": {"key": "TIMEOUT"},
        "top_workflow_stage": {"key": "reconciliation"},
        "top_workflow_status": {"key": "reconcile_blocked"},
        "top_reconciliation_block": {"key": "orphan_order_guard"},
    }
    engine._last_tuning_summary = {"applied": [{"section": "ai_core_runtime", "key": "min_rr_to_trade"}]}
    engine._learning_analytics_summary = {
        "study_modules": {"strategy_logic": 1},
        "retrieval_accuracy": 1.0,
        "research_conversion_rate": 0.5,
        "review_completion_score": 1.0,
    }

    review = await engine.generate_weekly_research_review(force=True)
    assert review is not None
    assert "review_markdown" in review
    assert "本周主动回忆正确率" in review["review_markdown"]
    assert "决策 workflow 卡点：stage=reconciliation / status=reconcile_blocked" in review["review_markdown"]
    assert "本周主要对账阻断：orphan_order_guard" in review["review_markdown"]
    assert review["workflow_focus"]["top_workflow_stage"]["key"] == "reconciliation"
    assert any(item[0] == "save_knowledge_document" for item in mm.saved)


@pytest.mark.asyncio
async def test_generate_retrieval_practice_deck_has_cards():
    mm = _FakeMemoryManager()
    engine = AILearningEngine(memory_manager=mm)
    engine.lessons = [
        TradingLesson(
            id="1",
            lesson_type=LessonType.SUCCESS_PATTERN,
            title="BTC success",
            content="only trade trend continuation with healthy liquidity",
            context={"strategy": "s1"},
            impact_score=0.8,
            confidence=0.9,
        )
    ]
    deck = await engine.generate_retrieval_practice_deck(limit=5)
    assert len(deck["cards"]) >= 3
    assert any("question" in card and "answer" in card for card in deck["cards"])


@pytest.mark.asyncio
async def test_update_strategy_learning_governance_marks_degraded():
    mm = _FakeMemoryManager()
    sm = StrategyManager(None)
    await sm.load_strategy_config(
        {
            "strategy_id": "s1",
            "name": "S1",
            "strategy_type": "ai_generated",
            "metadata": {"deployment": {"stage": "small", "cap_multiplier": 0.5}},
        }
    )
    engine = AILearningEngine(memory_manager=mm)
    engine.main_controller = SimpleNamespace(strategy_manager=sm)
    engine.lessons = [
        TradingLesson(
            id="1",
            lesson_type=LessonType.FAILURE_PATTERN,
            title="loss-1",
            content="bad",
            context={"strategy": "s1"},
            impact_score=-0.8,
            confidence=0.9,
        ),
        TradingLesson(
            id="2",
            lesson_type=LessonType.RISK_LESSON,
            title="loss-2",
            content="bad2",
            context={"strategy": "s1"},
            impact_score=-0.6,
            confidence=0.9,
        ),
    ]

    await engine._update_strategy_learning_governance()
    profile = sm.get_strategy_governance_profile("s1")
    assert profile["stage"] == StrategyLifecycleStage.DEGRADED.value
    assert profile["live_drift_status"] == "degraded"


@pytest.mark.asyncio
async def test_analyze_decision_traces_includes_workflow_signals():
    mm = _FakeMemoryManager()
    store = DecisionTraceStore(max_items=20, persist_path="")
    store.record_reconciliation_result(
        trace_id="t1",
        status="blocked",
        detail="side_mismatch_guard",
        extras={"symbol": "BTC/USDT"},
    )
    store.record_reconciliation_result(
        trace_id="t2",
        status="blocked",
        detail="orphan_order_guard",
        extras={"symbol": "ETH/USDT"},
    )

    engine = AILearningEngine(memory_manager=mm)
    engine.main_controller = SimpleNamespace(decision_trace_store=store)

    await engine._analyze_decision_traces()

    trace_feedback = engine._trace_feedback_summary
    self_review = engine._self_review_summary
    assert trace_feedback["top_workflow_stage"]["key"] == "reconciliation"
    assert trace_feedback["top_workflow_status"]["key"] == "reconcile_blocked"
    assert any("reconciliation 阶段" in item for item in trace_feedback["recommendations"])
    assert "reconciliation" in self_review["lesson_summary"]
    assert "reconcile_blocked" in self_review["mistake_tags"]
