from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import Settings, SettingsError, load_settings
from handlers import create_captcha_router, create_join_request_router
from services.captcha_service import CaptchaService


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def build_dispatcher(
    settings: Settings, service: CaptchaService
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(create_join_request_router(settings, service))
    dispatcher.include_router(create_captcha_router(settings, service))
    return dispatcher


async def main() -> None:
    configure_logging()
    settings = load_settings()
    service = CaptchaService(ttl_seconds=270, max_attempts=5)
    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher(settings, service)
    await dispatcher.start_polling(
        bot,
        allowed_updates=["chat_join_request", "callback_query"],
    )


def run() -> None:
    try:
        asyncio.run(main())
    except SettingsError as error:
        raise SystemExit(f"Configuration error: {error}") from error


if __name__ == "__main__":
    run()

