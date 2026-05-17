import pytest

from src.modules.core import enhanced_llm_manager as llm_module
from src.modules.core.enhanced_llm_manager import (
    EnhancedLLMManager,
    LLMResponse,
    ModelConfig,
    ModelProvider,
    TaskType,
)


def _mgr() -> EnhancedLLMManager:
    mgr = EnhancedLLMManager()
    mgr._initialized = True
    return mgr


def test_quota_circuit_break_marks_same_provider_group_unhealthy():
    mgr = _mgr()
    shared_base = "https://api.deepseek.com/v1"
    shared_key = "same-key"
    mgr.models["deepseek-v4-flash"] = ModelConfig(ModelProvider.OPENAI, "deepseek-v4-flash", "flash", api_key=shared_key, base_url=shared_base, enabled=True)
    mgr.models["deepseek-v4-pro"] = ModelConfig(ModelProvider.OPENAI, "deepseek-v4-pro", "pro", api_key=shared_key, base_url=shared_base, enabled=True)
    mgr.models["astron-code-latest"] = ModelConfig(ModelProvider.OPENAI, "astron-code-latest", "astron", api_key="other", base_url="https://example.com/v1", enabled=True)

    resp = LLMResponse(content="", model_id="deepseek-v4-flash", provider=ModelProvider.OPENAI, success=False, error_code="QUOTA_EXCEEDED")
    mgr._apply_failure_circuit_break("deepseek-v4-flash", resp, TaskType.GENERAL)

    assert not mgr._is_model_healthy("deepseek-v4-flash")
    assert not mgr._is_model_healthy("deepseek-v4-pro")
    assert mgr._is_model_healthy("astron-code-latest")


@pytest.mark.asyncio
async def test_select_model_returns_none_when_all_task_candidates_unhealthy():
    mgr = _mgr()
    for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
        mgr.models[model_id] = ModelConfig(ModelProvider.OPENAI, model_id, model_id, enabled=True)
        mgr.providers[model_id] = object()
        mgr._unhealthy_until[model_id] = 10**12
    mgr.task_model_mapping[TaskType.DECISION_MAKING] = ["deepseek-v4-flash", "deepseek-v4-pro"]

    selected = await mgr.select_model(TaskType.DECISION_MAKING)

    assert selected is None


@pytest.mark.asyncio
async def test_generate_returns_explicit_no_healthy_model_error():
    mgr = _mgr()
    for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
        mgr.models[model_id] = ModelConfig(ModelProvider.OPENAI, model_id, model_id, enabled=True)
        mgr.providers[model_id] = object()
        mgr._unhealthy_until[model_id] = 10**12
    mgr.task_model_mapping[TaskType.DECISION_MAKING] = ["deepseek-v4-flash", "deepseek-v4-pro"]

    resp = await mgr.generate("hi", task_type=TaskType.DECISION_MAKING)

    assert not resp.success
    assert resp.error_code == "NO_HEALTHY_MODEL"
    assert resp.task_type == TaskType.DECISION_MAKING


def test_network_failures_backoff_exponentially(monkeypatch):
    mgr = _mgr()
    mgr.models["deepseek-v4-flash"] = ModelConfig(
        ModelProvider.OPENAI,
        "deepseek-v4-flash",
        "flash",
        enabled=True,
    )
    resp = LLMResponse(
        content="",
        model_id="deepseek-v4-flash",
        provider=ModelProvider.OPENAI,
        success=False,
        error_code="NETWORK_ERROR",
    )
    now = [1000.0]
    monkeypatch.setattr(llm_module.time, "time", lambda: now[0])
    monkeypatch.setenv("OPENCLAW_LLM_CB_NETWORK_SEC", "30")
    monkeypatch.setenv("OPENCLAW_LLM_CB_MAX_SEC", "300")

    mgr._apply_failure_circuit_break("deepseek-v4-flash", resp, TaskType.GENERAL)
    assert mgr._unhealthy_until["deepseek-v4-flash"] == pytest.approx(1030.0)

    now[0] = 2000.0
    mgr._apply_failure_circuit_break("deepseek-v4-flash", resp, TaskType.GENERAL)
    assert mgr._unhealthy_until["deepseek-v4-flash"] == pytest.approx(2060.0)

    mgr._clear_model_unhealthy("deepseek-v4-flash")
    assert "deepseek-v4-flash" not in mgr._consecutive_failures
