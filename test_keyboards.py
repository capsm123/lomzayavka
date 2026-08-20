from keyboards.captcha import (
    CaptchaAnswerCallback,
    CaptchaStartCallback,
    answer_keyboard,
    start_keyboard,
)


def test_start_keyboard_contains_only_opaque_captcha_id() -> None:
    markup = start_keyboard("opaqueXYZ")
    button = markup.inline_keyboard[0][0]

    payload = CaptchaStartCallback.unpack(button.callback_data or "")
    assert button.text == "🤖 Я не робот"
    assert payload.captcha_id == "opaqueXYZ"
    assert set(type(payload).model_fields) == {"captcha_id"}


def test_answer_keyboard_uses_indices_without_exposing_answers() -> None:
    options = (10, 12, 13, 15)

    markup = answer_keyboard("opaqueXYZ", options)
    buttons = [button for row in markup.inline_keyboard for button in row]
    payloads = [
        CaptchaAnswerCallback.unpack(button.callback_data or "") for button in buttons
    ]

    assert [[button.text for button in row] for row in markup.inline_keyboard] == [
        ["10", "12"],
        ["13", "15"],
    ]
    assert [payload.option_index for payload in payloads] == [0, 1, 2, 3]
    assert all(payload.captcha_id == "opaqueXYZ" for payload in payloads)
    assert all(
        set(type(payload).model_fields) == {"captcha_id", "option_index"}
        for payload in payloads
    )
    assert all("12" not in (button.callback_data or "") for button in buttons)
