from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class CaptchaStartCallback(CallbackData, prefix="cs"):
    captcha_id: str


class CaptchaAnswerCallback(CallbackData, prefix="ca"):
    captcha_id: str
    option_index: int


def start_keyboard(captcha_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 Я не робот",
                    callback_data=CaptchaStartCallback(captcha_id=captcha_id).pack(),
                )
            ]
        ]
    )


def answer_keyboard(
    captcha_id: str, options: tuple[int, int, int, int]
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=str(option),
            callback_data=CaptchaAnswerCallback(
                captcha_id=captcha_id, option_index=index
            ).pack(),
        )
        for index, option in enumerate(options)
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[buttons[:2], buttons[2:]],
    )

