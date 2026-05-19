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


def _task_key(mgr: EnhancedLLMManager, model_id: str, task_type: TaskType) -> str:
    return mgr._task_health_key(model_id, task_type)


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
async def test_select_model_probes_once_when_all_task_candidates_unhealthy(monkeypatch):
    mgr = _mgr()
    for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
        mgr.models[model_id] = ModelConfig(ModelProvider.OPENAI, model_id, model_id, enabled=True)
        mgr.providers[model_id] = object()
        mgr._unhealthy_until[_task_key(mgr, model_id, TaskType.DECISION_MAKING)] = 10**12
    mgr.task_model_mapping[TaskType.DECISION_MAKING] = ["deepseek-v4-flash", "deepseek-v4-pro"]
    monkeypatch.setenv("OPENCLAW_LLM_CB_ALL_UNHEALTHY_PROBE_SEC", "30")

    selected = await mgr.select_model(TaskType.DECISION_MAKING)

    assert selected == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_select_model_returns_none_during_all_unhealthy_probe_cooldown(monkeypatch):
    mgr = _mgr()
    for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
        mgr.models[model_id] = ModelConfig(ModelProvider.OPENAI, model_id, model_id, enabled=True)
        mgr.providers[model_id] = object()
        mgr._unhealthy_until[_task_key(mgr, model_id, TaskType.DECISION_MAKING)] = 10**12
    mgr.task_model_mapping[TaskType.DECISION_MAKING] = ["deepseek-v4-flash", "deepseek-v4-pro"]
    monkeypatch.setenv("OPENCLAW_LLM_CB_ALL_UNHEALTHY_PROBE_SEC", "30")

    first = await mgr.select_model(TaskType.DECISION_MAKING)
    second = await mgr.select_model(TaskType.DECISION_MAKING)

    assert first == "deepseek-v4-flash"
    assert second is None


@pytest.mark.asyncio
async def test_generate_returns_explicit_no_healthy_model_error_when_probe_disabled(monkeypatch):
    mgr = _mgr()
    for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
        mgr.models[model_id] = ModelConfig(ModelProvider.OPENAI, model_id, model_id, enabled=True)
        mgr.providers[model_id] = object()
        mgr._unhealthy_until[_task_key(mgr, model_id, TaskType.DECISION_MAKING)] = 10**12
    mgr.task_model_mapping[TaskType.DECISION_MAKING] = ["deepseek-v4-flash", "deepseek-v4-pro"]
    monkeypatch.setenv("OPENCLAW_LLM_CB_ALL_UNHEALTHY_PROBE_SEC", "0")

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
    key = _task_key(mgr, "deepseek-v4-flash", TaskType.GENERAL)

    mgr._apply_failure_circuit_break("deepseek-v4-flash", resp, TaskType.GENERAL)
    assert mgr._unhealthy_until[key] == pytest.approx(1030.0)

    now[0] = 2000.0
    mgr._apply_failure_circuit_break("deepseek-v4-flash", resp, TaskType.GENERAL)
    assert mgr._unhealthy_until[key] == pytest.approx(2060.0)

    mgr._clear_model_unhealthy("deepseek-v4-flash", TaskType.GENERAL)
    assert _task_key(mgr, "deepseek-v4-flash", TaskType.GENERAL) not in mgr._consecutive_failures


@pytest.mark.asyncio
async def test_generate_fallback_stays_within_task_mapping(monkeypatch):
    mgr = _mgr()
    for model_id, priority in (
        ("astron-code-latest", 10),
        ("qianfan-code-latest", 5),
        ("deepseek-v4-pro", 99),
    ):
        mgr.models[model_id] = ModelConfig(
            ModelProvider.OPENAI,
            model_id,
            model_id,
            enabled=True,
            priority=priority,
        )
        mgr.providers[model_id] = object()
    mgr.task_model_mapping[TaskType.GENERAL] = ["astron-code-latest", "qianfan-code-latest"]

    calls = []

    async def _fake_generate(prompt, model_id, task_type, **kwargs):
        calls.append(model_id)
        return LLMResponse(
            content="",
            model_id=model_id,
            provider=ModelProvider.OPENAI,
            task_type=task_type,
            success=False,
            error_code="HTTP_ERROR",
        )

    monkeypatch.setattr(mgr, "_generate_with_model", _fake_generate)

    resp = await mgr.generate(
        "hello",
        model_id="astron-code-latest",
        task_type=TaskType.GENERAL,
        use_fallback=True,
    )

    assert not resp.success
    assert calls == ["astron-code-latest", "qianfan-code-latest"]
