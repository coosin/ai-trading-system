from src.modules.research.strategy_research_pipeline import StrategyResearchPipeline


def test_strategy_research_pipeline_initializes_resource_guards():
    pipeline = StrategyResearchPipeline()

    assert pipeline.max_parallel_symbols == 2
    assert pipeline.max_candidates_per_symbol == 12
    assert pipeline.max_backtests_per_cycle == 240
    assert pipeline.per_symbol_time_budget_sec == 25.0
    assert pipeline._symbol_semaphore is not None
