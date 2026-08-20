from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from dotenv import load_dotenv


class SettingsError(ValueError):
    """Raised when required application settings are missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    channel_id: int


def load_settings(environment: Mapping[str, str] | None = None) -> Settings:
    if environment is None:
        load_dotenv()
        environment = os.environ

    bot_token = environment.get("BOT_TOKEN", "").strip()
    if not bot_token:
        raise SettingsError("BOT_TOKEN is required and must not be blank")

    raw_channel_id = environment.get("CHANNEL_ID", "").strip()
    if not raw_channel_id:
        raise SettingsError("CHANNEL_ID is required")
    try:
        channel_id = int(raw_channel_id)
    except ValueError as error:
        raise SettingsError("CHANNEL_ID must be a signed integer") from error
    if channel_id >= 0:
        raise SettingsError("CHANNEL_ID must be a negative Telegram chat ID")

    return Settings(bot_token=bot_token, channel_id=channel_id)

