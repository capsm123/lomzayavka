import pytest

from config import SettingsError, load_settings


def test_load_settings_parses_signed_channel_id() -> None:
    settings = load_settings({"BOT_TOKEN": "token", "CHANNEL_ID": "-1001234567890"})

    assert settings.bot_token == "token"
    assert settings.channel_id == -1001234567890


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"CHANNEL_ID": "-1001"}, "BOT_TOKEN"),
        ({"BOT_TOKEN": "token"}, "CHANNEL_ID"),
        ({"BOT_TOKEN": " ", "CHANNEL_ID": "-1001"}, "BOT_TOKEN"),
        ({"BOT_TOKEN": "token", "CHANNEL_ID": "channel"}, "signed integer"),
        ({"BOT_TOKEN": "token", "CHANNEL_ID": "1001"}, "negative"),
    ],
)
def test_load_settings_rejects_invalid_environment(
    environment: dict[str, str], message: str
) -> None:
    with pytest.raises(SettingsError, match=message):
        load_settings(environment)

