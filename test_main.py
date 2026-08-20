from unittest.mock import AsyncMock, Mock

import pytest

import main
from config import Settings
from services.captcha_service import CaptchaService


def test_build_dispatcher_registers_both_feature_routers() -> None:
    dispatcher = main.build_dispatcher(
        Settings(bot_token="123456:test-token", channel_id=-1001),
        CaptchaService(),
    )

    assert [router.name for router in dispatcher.sub_routers] == [
        "join_requests",
        "captcha",
    ]


@pytest.mark.asyncio
async def test_main_starts_polling_only_required_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(bot_token="123456:test-token", channel_id=-1001)
    bot = Mock()
    dispatcher = Mock()
    dispatcher.start_polling = AsyncMock()
    monkeypatch.setattr(main, "load_settings", Mock(return_value=settings))
    monkeypatch.setattr(main, "Bot", Mock(return_value=bot))
    monkeypatch.setattr(main, "build_dispatcher", Mock(return_value=dispatcher))

    await main.main()

    dispatcher.start_polling.assert_awaited_once_with(
        bot,
        allowed_updates=["chat_join_request", "callback_query"],
    )

