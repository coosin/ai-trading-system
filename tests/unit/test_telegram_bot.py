import pytest

from src.modules.notification.telegram_bot import TelegramBot, TelegramResponse


@pytest.mark.asyncio
async def test_send_message_accepts_text_only_uses_first_chat_id():
    bot = TelegramBot({"enabled": True, "chat_ids": [12345], "bot_token": "dummy"})
    sent = {}

    async def _fake_send(response: TelegramResponse):
        sent["chat_id"] = response.chat_id
        sent["text"] = response.text

    bot._send_message = _fake_send
    await bot.send_message("hello world")

    assert sent["chat_id"] == 12345
    assert sent["text"] == "hello world"


@pytest.mark.asyncio
async def test_send_message_explicit_chat_id_still_supported():
    bot = TelegramBot({"enabled": True, "chat_ids": [12345], "bot_token": "dummy"})
    sent = {}

    async def _fake_send(response: TelegramResponse):
        sent["chat_id"] = response.chat_id
        sent["text"] = response.text

    bot._send_message = _fake_send
    await bot.send_message(67890, "explicit target")

    assert sent["chat_id"] == 67890
    assert sent["text"] == "explicit target"
