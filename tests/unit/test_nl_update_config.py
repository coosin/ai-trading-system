import pytest


class _FakeConfigManager:
    def __init__(self):
        self.calls = []

    async def set_config_path(self, path: str, value, validate: bool = True):
        self.calls.append((path, value, validate))
        return True


class _FakeMC:
    def __init__(self):
        self.config_manager = _FakeConfigManager()
        self.memory_gateway = None

    async def log_audit_event(self, *args, **kwargs):
        return "ok"


@pytest.mark.asyncio
async def test_nl_update_config_applies_whitelisted_paths():
    from src.modules.intelligence.natural_language_interface import NaturalLanguageInterface

    mc = _FakeMC()
    nli = NaturalLanguageInterface(llm_integration=None, main_controller=mc)  # type: ignore[arg-type]

    # direct call internal executor (no LLM needed)
    res = await nli._execute_update_config(
        query="把心跳改成10分钟，把 high 通知冷却改成20分钟",
        params={
            "changes": [
                {"path": "heartbeat.interval_sec", "value": 600},
                {"path": "notifications.smart.dedup_windows_sec.high", "value": 1200},
                {"path": "paths.base_path", "value": "/tmp/hack"},
            ]
        },
    )

    assert res["success"] is True
    assert len(res["data"]["applied"]) == 2
    assert len(res["data"]["rejected"]) == 1
    assert mc.config_manager.calls[0][0] == "heartbeat.interval_sec"
    assert mc.config_manager.calls[1][0] == "notifications.smart.dedup_windows_sec.high"


@pytest.mark.asyncio
async def test_nl_update_config_denies_secrets_like_tokens():
    from src.modules.intelligence.natural_language_interface import NaturalLanguageInterface

    mc = _FakeMC()
    nli = NaturalLanguageInterface(llm_integration=None, main_controller=mc)  # type: ignore[arg-type]
    res = await nli._execute_update_config(
        query="把telegram token改一下",
        params={"changes": [{"path": "notifications.telegram.token", "value": "abc"}]},
    )
    assert res["success"] is False
    assert len(res["data"]["applied"]) == 0
    assert len(res["data"]["rejected"]) == 1

