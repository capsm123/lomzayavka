from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatJoinRequest

from config import Settings
from keyboards.captcha import start_keyboard
from services.captcha_service import CaptchaService

logger = logging.getLogger(__name__)

GREETING_TEXT = (
    "👋 Вы подали заявку на вступление в канал.\n\n"
    "Чтобы подтвердить, что вы не робот, пройдите небольшую проверку."
)


async def handle_join_request(
    request: ChatJoinRequest,
    bot: Bot,
    settings: Settings,
    service: CaptchaService,
) -> None:
    if request.chat.id != settings.channel_id:
        return

    user_id = request.from_user.id
    logger.info(
        "Join request received: user_id=%s chat_id=%s",
        user_id,
        request.chat.id,
    )
    created = await service.create_request(
        chat_id=request.chat.id,
        user_id=user_id,
        user_chat_id=request.user_chat_id,
        request_timestamp=request.date.timestamp(),
    )
    if not created.is_new:
        logger.info("Duplicate join request ignored: user_id=%s", user_id)
        return

    try:
        await bot.send_message(
            chat_id=request.user_chat_id,
            text=GREETING_TEXT,
            reply_markup=start_keyboard(created.state.captcha_id),
        )
        logger.info("Captcha sent: user_id=%s", user_id)
    except TelegramAPIError:
        logger.exception(
            "Telegram API error while sending CAPTCHA: user_id=%s chat_id=%s",
            user_id,
            request.chat.id,
        )
        await service.discard(
            request.chat.id, user_id, created.state.captcha_id
        )
        try:
            await bot.decline_chat_join_request(
                chat_id=request.chat.id, user_id=user_id
            )
            logger.info("Join request declined after send failure: user_id=%s", user_id)
        except TelegramAPIError:
            logger.exception(
                "Telegram API error while declining undeliverable request: user_id=%s",
                user_id,
            )


def create_join_request_router(
    settings: Settings, service: CaptchaService
) -> Router:
    router = Router(name="join_requests")

    @router.chat_join_request()
    async def on_join_request(request: ChatJoinRequest, bot: Bot) -> None:
        await handle_join_request(request, bot, settings, service)

    return router

