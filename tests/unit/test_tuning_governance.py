import pytest

from src.modules.core.tuning_governance import TuningGovernance


class _FakeConfigManager:
    def __init__(self):
        self.writes = []

    async def set_config(self, section, key, value):
        self.writes.append((section, key, value))


@pytest.mark.asyncio
async def test_tuning_governance_applies_only_whitelisted_items(tmp_path):
    cm = _FakeConfigManager()
    gov = TuningGovernance(cm, persist_path=str(tmp_path / "tgov.json"))
    result = await gov.evaluate_and_apply(
        [
            {"section": "ai_core_runtime", "key": "ai_core_min_confidence_to_open", "new": 0.75},
            {"section": "ai_core_runtime", "key": "forbidden_key", "new": 0.75},
        ],
        source="test",
    )
    assert len(result["applied"]) == 1
    assert len(result["rejected"]) == 1
    assert cm.writes == [("ai_core_runtime", "ai_core_min_confidence_to_open", 0.75)]
