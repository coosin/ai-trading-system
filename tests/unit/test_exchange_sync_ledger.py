import json

import pytest

from src.modules.core import exchange_sync_ledger as ledger


@pytest.mark.asyncio
async def test_append_exchange_truth_dedupes_identical_events(tmp_path, monkeypatch):
    ledger._recent_append_fingerprints.clear()
    ledger._persisted_dedupe_keys.clear()
    ledger._persisted_dedupe_loaded_for = ""
    writes = []

    class _Writer:
        async def write(self, payload: str) -> None:
            writes.append(payload)

    class _OpenCtx:
        async def __aenter__(self):
            return _Writer()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(ledger, "_resolve_ledger_path", lambda: tmp_path / "exchange_truth.jsonl")
    monkeypatch.setattr(ledger.aiofiles, "open", lambda *args, **kwargs: _OpenCtx())

    event = {
        "event": "auto_truth_backfill",
        "symbol": "BTC/USDT",
        "order_id": "ord-1",
        "exchange_fill_count": 2,
        "exchange_pnl": 12.5,
        "exchange_fee": -0.3,
        "exchange_price": 50000.0,
    }
    await ledger.append_exchange_truth(dict(event))
    await ledger.append_exchange_truth(dict(event))

    rows = [json.loads(line) for line in writes if line.strip()]
    assert len(rows) == 1
    assert rows[0]["event"] == "auto_truth_backfill"
    assert rows[0]["order_id"] == "ord-1"


@pytest.mark.asyncio
async def test_append_exchange_truth_dedupes_against_existing_ledger_rows(tmp_path, monkeypatch):
    ledger._recent_append_fingerprints.clear()
    ledger._persisted_dedupe_keys.clear()
    ledger._persisted_dedupe_loaded_for = ""
    path = tmp_path / "exchange_truth.jsonl"
    existing = {
        "ts_utc": "2026-05-18T10:12:34+00:00",
        "channel": "exchange_truth",
        "event": "trade_close_recorded",
        "symbol": "ATOM/USDT/SWAP",
        "side": "long",
        "order_id": "c1",
        "price": 1.93,
        "quantity": 2.0,
        "pnl": -0.142,
        "fee": -0.00193,
        "pnl_estimated": False,
        "fills_enriched": False,
        "source": "stop_loss_take_profit",
    }
    path.write_text(json.dumps(existing, ensure_ascii=False) + "\n", encoding="utf-8")
    writes = []

    class _Writer:
        async def write(self, payload: str) -> None:
            writes.append(payload)

    class _OpenCtx:
        async def __aenter__(self):
            return _Writer()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(ledger, "_resolve_ledger_path", lambda: path)
    monkeypatch.setattr(ledger.aiofiles, "open", lambda *args, **kwargs: _OpenCtx())

    await ledger.append_exchange_truth({k: v for k, v in existing.items() if k not in {"ts_utc", "channel"}})

    assert writes == []
