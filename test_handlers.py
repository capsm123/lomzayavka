import asyncio
import random
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import Settings
from handlers.captcha import handle_captcha_answer, handle_captcha_start
from handlers.join_requests import handle_join_request
from keyboards.captcha import CaptchaAnswerCallback, CaptchaStartCallback
from services.captcha_service import CaptchaService


@pytest.fixture
def settings() -> Settings:
    return Settings(bot_token="123456:test-token", channel_id=-1001)


@pytest.fixture
def now() -> list[float]:
    return [1_000_000.0]


@pytest.fixture
def service(now: list[float]) -> CaptchaService:
    return CaptchaService(clock=lambda: now[0], rng=random.Random(2026))


def make_join_request(chat_id: int = -1001) -> SimpleNamespace:
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=42),
        user_chat_id=9001,
        date=datetime.fromtimestamp(999_990.0, tz=timezone.utc),
    )


def make_callback(user_id: int = 42) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(message_id=77),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_foreign_channel_join_request_is_ignored(
    settings: Settings, service: CaptchaService
) -> None:
    bot = AsyncMock()

    await handle_join_request(make_join_request(-2002), bot, settings, service)

    bot.send_message.assert_not_awaited()
    assert await service.get_state(-2002, 42) is None


@pytest.mark.asyncio
async def test_join_request_sends_one_challenge_for_duplicate_update(
    settings: Settings, service: CaptchaService
) -> None:
    bot = AsyncMock()
    request = make_join_request()

    await handle_join_request(request, bot, settings, service)
    await handle_join_request(request, bot, settings, service)

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == 9001
    markup = bot.send_message.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].text == "🤖 Я не робот"


@pytest.mark.asyncio
async def test_start_callback_replaces_greeting_with_question(
    settings: Settings, service: CaptchaService
) -> None:
    bot = AsyncMock()
    created = await service.create_request(-1001, 42, 9001, 999_990.0)
    callback = make_callback()

    await handle_captcha_start(
        callback,
        CaptchaStartCallback(captcha_id=created.state.captcha_id),
        bot,
        settings,
        service,
    )

    callback.answer.assert_awaited_once_with()
    bot.edit_message_text.assert_awaited_once()
    assert "🧮 Решите пример" in bot.edit_message_text.await_args.kwargs["text"]
    assert bot.edit_message_text.await_args.kwargs["chat_id"] == 9001


async def create_active_question(
    service: CaptchaService,
) -> tuple[str, int]:
    created = await service.create_request(-1001, 42, 9001, 999_990.0)
    started = await service.start(-1001, 42, created.state.captcha_id)
    assert started.state is not None
    assert started.question is not None
    return started.state.captcha_id, started.question.correct_index


@pytest.mark.asyncio
async def test_four_wrong_answers_never_approve_request(
    settings: Settings, service: CaptchaService
) -> None:
    bot = AsyncMock()
    captcha_id, correct_index = await create_active_question(service)

    for _ in range(4):
        wrong_index = next(index for index in range(4) if index != correct_index)
        await handle_captcha_answer(
            make_callback(),
            CaptchaAnswerCallback(
                captcha_id=captcha_id, option_index=wrong_index
            ),
            bot,
            settings,
            service,
        )
        state = await service.get_state(-1001, 42)
        assert state is not None
        assert state.question is not None
        captcha_id = state.captcha_id
        correct_index = state.question.correct_index

    bot.approve_chat_join_request.assert_not_awaited()
    bot.decline_chat_join_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_fifth_wrong_answer_declines_and_clears_request(
    settings: Settings, service: CaptchaService
) -> None:
    bot = AsyncMock()
    captcha_id, correct_index = await create_active_question(service)

    for _ in range(5):
        wrong_index = next(index for index in range(4) if index != correct_index)
        await handle_captcha_answer(
            make_callback(),
            CaptchaAnswerCallback(
                captcha_id=captcha_id, option_index=wrong_index
            ),
            bot,
            settings,
            service,
        )
        state = await service.get_state(-1001, 42)
        if state is not None and state.question is not None:
            captcha_id = state.captcha_id
            correct_index = state.question.correct_index

    bot.approve_chat_join_request.assert_not_awaited()
    bot.decline_chat_join_request.assert_awaited_once_with(
        chat_id=-1001, user_id=42
    )
    assert await service.get_state(-1001, 42) is None


@pytest.mark.asyncio
async def test_correct_answer_approves_exactly_once_under_concurrency(
    settings: Settings, service: CaptchaService
) -> None:
    bot = AsyncMock()
    captcha_id, correct_index = await create_active_question(service)
    callback_data = CaptchaAnswerCallback(
        captcha_id=captcha_id, option_index=correct_index
    )

    await asyncio.gather(
        handle_captcha_answer(
            make_callback(), callback_data, bot, settings, service
        ),
        handle_captcha_answer(
            make_callback(), callback_data, bot, settings, service
        ),
    )

    bot.approve_chat_join_request.assert_awaited_once_with(
        chat_id=-1001, user_id=42
    )
    bot.decline_chat_join_request.assert_not_awaited()
    assert await service.get_state(-1001, 42) is None


@pytest.mark.asyncio
async def test_forged_callback_from_other_user_cannot_approve(
    settings: Settings, service: CaptchaService
) -> None:
    bot = AsyncMock()
    captcha_id, correct_index = await create_active_question(service)
    callback = make_callback(user_id=99)

    await handle_captcha_answer(
        callback,
        CaptchaAnswerCallback(
            captcha_id=captcha_id, option_index=correct_index
        ),
        bot,
        settings,
        service,
    )

    bot.approve_chat_join_request.assert_not_awaited()
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_start_declines_and_clears_request(
    settings: Settings, service: CaptchaService, now: list[float]
) -> None:
    bot = AsyncMock()
    created = await service.create_request(-1001, 42, 9001, 999_990.0)
    now[0] = 1_000_300.0

    await handle_captcha_start(
        make_callback(),
        CaptchaStartCallback(captcha_id=created.state.captcha_id),
        bot,
        settings,
        service,
    )

    bot.decline_chat_join_request.assert_awaited_once_with(
        chat_id=-1001, user_id=42
    )
    bot.approve_chat_join_request.assert_not_awaited()
    assert await service.get_state(-1001, 42) is None

