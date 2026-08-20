# Telegram CAPTCHA Join Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable aiogram 3.x bot that approves private-channel join requests only after a secure arithmetic CAPTCHA.

**Architecture:** Thin aiogram routers translate Telegram updates into operations on an in-memory `CaptchaService`. The service owns opaque CAPTCHA state and per-applicant locks; handlers perform Telegram API calls only after server-side validation.

**Tech Stack:** Python 3.11+, aiogram 3.x, asyncio, python-dotenv, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-08-20-telegram-captcha-join-bot-design.md`

## Global Constraints

- CAPTCHA lifetime is 270 seconds from the Telegram join-request timestamp.
- Five wrong answers decline the request.
- Only the signed integer `CHANNEL_ID` from `.env` is handled.
- Callback data never contains the correct answer, trusted user ID, or channel ID.
- State is stored in RAM behind a service boundary suitable for later Redis replacement.
- Telegram API errors are logged and never terminate polling.

---

### Task 1: Configuration and CAPTCHA domain service

**Files:**
- Create: `config.py`
- Create: `services/__init__.py`
- Create: `services/captcha_service.py`
- Create: `tests/test_config.py`
- Create: `tests/test_captcha_service.py`

**Interfaces:**
- Produces: `Settings(bot_token: str, channel_id: int)`, `load_settings() -> Settings`
- Produces: `CaptchaService(ttl_seconds=270, max_attempts=5, clock=...)`
- Produces: async `create_request`, `start`, `answer`, `discard`, and `locked_state` operations.

- [x] **Step 1: Write failing configuration and service tests**

Cover missing/blank variables, signed integer channel parsing, generated result range,
unique choices, nonnegative subtraction, duplicate request reuse, opaque-ID mismatch,
ownership mismatch, expiry, and five attempts.

```python
def test_question_has_four_unique_choices(service):
    question = service.generate_question()
    assert len(question.options) == len(set(question.options)) == 4
    assert question.options[question.correct_index] == question.answer

@pytest.mark.asyncio
async def test_fifth_wrong_answer_exhausts_request(service, state):
    for _ in range(4):
        result = await service.answer(state.chat_id, state.user_id, state.captcha_id, wrong_index(state))
        assert result.status is AnswerStatus.WRONG
    result = await service.answer(state.chat_id, state.user_id, state.captcha_id, wrong_index(state))
    assert result.status is AnswerStatus.EXHAUSTED
```

- [x] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_config.py tests/test_captcha_service.py -v`
Expected: collection fails because modules do not exist.

- [x] **Step 3: Implement configuration and service**

Use frozen dataclasses and enums. Generate opaque IDs with `secrets.token_urlsafe(9)`.
Key states by `(chat_id, user_id)` and locks by the same key. Define explicit results:

```python
class AnswerStatus(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"
    INVALID = "invalid"

async def answer(
    self, chat_id: int, user_id: int, captcha_id: str, option_index: int
) -> AnswerResult: ...
```

`answer` runs under the per-key lock, validates the stored channel, user, opaque ID,
status, TTL, and option index, then changes state atomically.

- [x] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_config.py tests/test_captcha_service.py -v`
Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add config.py services tests/test_config.py tests/test_captcha_service.py
git commit -m "feat: add configuration and CAPTCHA service"
```

### Task 2: Callback protocol and keyboards

**Files:**
- Create: `keyboards/__init__.py`
- Create: `keyboards/captcha.py`
- Create: `tests/test_keyboards.py`

**Interfaces:**
- Consumes: CAPTCHA IDs and `CaptchaQuestion.options` from Task 1.
- Produces: `start_keyboard(captcha_id)`, `answer_keyboard(captcha_id, options)`.
- Produces: aiogram `CallbackData` classes `CaptchaStartCallback` and `CaptchaAnswerCallback`.

- [x] **Step 1: Write failing keyboard tests**

```python
def test_answer_callbacks_do_not_expose_answers(question):
    markup = answer_keyboard("opaque123", question.options)
    payloads = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert all(str(question.answer) not in payload for payload in payloads)
    assert len(payloads) == 4
```

Also unpack each payload and assert it contains only prefix, opaque ID, and index.

- [x] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_keyboards.py -v`
Expected: collection fails because keyboard module does not exist.

- [x] **Step 3: Implement typed callback factories and keyboards**

```python
class CaptchaAnswerCallback(CallbackData, prefix="ca"):
    captcha_id: str
    option_index: int
```

Build a 2-by-2 answer layout and a one-button start layout.

- [x] **Step 4: Run keyboard tests**

Run: `python -m pytest tests/test_keyboards.py -v`
Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add keyboards tests/test_keyboards.py
git commit -m "feat: add secure CAPTCHA keyboards"
```

### Task 3: Join-request and CAPTCHA handlers

**Files:**
- Create: `handlers/__init__.py`
- Create: `handlers/join_requests.py`
- Create: `handlers/captcha.py`
- Create: `tests/test_handlers.py`

**Interfaces:**
- Consumes: `Settings`, `CaptchaService`, callback factories, and keyboard builders.
- Produces: `create_join_request_router(settings, service) -> Router`.
- Produces: `create_captcha_router(settings, service) -> Router`.

- [x] **Step 1: Write failing async handler tests**

Use `AsyncMock` bot methods and constructed aiogram objects. Assert a foreign channel
does nothing, a valid request sends to `user_chat_id`, four wrong choices never call
approve, a correct choice calls approve exactly once, the fifth wrong choice calls
decline, an expired callback declines, and duplicate callbacks cannot approve twice.

```python
assert bot.approve_chat_join_request.await_count == 1
bot.approve_chat_join_request.assert_awaited_once_with(
    chat_id=settings.channel_id, user_id=user_id
)
```

- [x] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_handlers.py -v`
Expected: collection fails because handlers do not exist.

- [x] **Step 3: Implement request handler**

Filter with `F.chat.id == settings.channel_id`, create one state, and send the greeting
to `request.user_chat_id`. On any Telegram send failure, discard state and safely try
`decline_chat_join_request`.

- [x] **Step 4: Implement callback handlers**

Validate `callback.from_user.id`, configured channel via stored state, opaque ID, active
status, and TTL. Always call `callback.answer()` promptly. Edit messages to remove old
buttons. Catch `TelegramBadRequest`, `TelegramForbiddenError`, and `TelegramAPIError`,
log context, and clear unsafe state.

- [x] **Step 5: Run handler and full tests**

Run: `python -m pytest tests/test_handlers.py -v`
Expected: all handler tests pass.

Run: `python -m pytest -v`
Expected: entire suite passes.

- [x] **Step 6: Commit**

```bash
git add handlers tests/test_handlers.py
git commit -m "feat: process join requests through CAPTCHA"
```

### Task 4: Application entry point and packaging

**Files:**
- Create: `main.py`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `tests/test_main.py`

**Interfaces:**
- Consumes: configuration, routers, and service.
- Produces: async `main() -> None` polling entry point.

- [x] **Step 1: Write failing wiring test**

Mock `Bot`, `Dispatcher.start_polling`, and settings. Verify both routers are included,
pending updates are preserved so a fresh queued join request can rebuild RAM state after
a restart, and allowed updates include only callback and join-request types.

- [x] **Step 2: Run test and verify failure**

Run: `python -m pytest tests/test_main.py -v`
Expected: import fails because `main.py` does not exist.

- [x] **Step 3: Implement entry point and environment files**

```python
async def main() -> None:
    settings = load_settings()
    service = CaptchaService()
    bot = Bot(settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_routers(...)
    await dispatcher.start_polling(bot, allowed_updates=["chat_join_request", "callback_query"])
```

Configure `logging.basicConfig`, use `asyncio.run(main())`, pin compatible dependency
ranges, ignore `.env`, virtual environments, caches, and coverage output.

- [x] **Step 4: Run tests and import checks**

Run: `python -m pytest tests/test_main.py -v`
Expected: pass.

Run: `python -m compileall -q .`
Expected: exit code 0.

- [x] **Step 5: Commit**

```bash
git add main.py requirements.txt .env.example .gitignore tests/test_main.py
git commit -m "feat: add runnable bot application"
```

### Task 5: Operations documentation and final verification

**Files:**
- Create: `README.md`
- Modify: tests only if verification exposes an implementation defect.

**Interfaces:**
- Consumes: final CLI, environment contract, Telegram permission requirements.
- Produces: complete installation, configuration, operation, and manual-test guide.

- [x] **Step 1: Write README**

Document BotFather creation, adding the bot as channel administrator with permission to
invite users (`can_invite_users`), creating an invite link with join requests enabled,
obtaining the `-100...` channel ID, `.env` setup, Python 3.11 virtual environment,
installation, polling startup, log interpretation, and an end-to-end test with correct,
wrong, stale, duplicate, and cancelled requests. State explicitly that `user_chat_id`
is usable for five minutes and this bot uses 270 seconds, and that restart loses RAM
state so applicants must resubmit.

- [x] **Step 2: Install declared dependencies**

Run: `python3.11 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`
Expected: dependencies install successfully.

- [x] **Step 3: Run final verification**

Run: `.venv/bin/python -m pytest -v`
Expected: all tests pass.

Run: `.venv/bin/python -m compileall -q main.py config.py handlers services keyboards`
Expected: exit code 0.

Run: `.venv/bin/python -c "import main, config, handlers, services, keyboards"`
Expected: exit code 0.

- [x] **Step 4: Audit security invariants**

Search callback payload code and confirm no correct answer, user ID, or channel ID is
serialized. Confirm every approve path follows service validation and every terminal
path removes state. Confirm `CHANNEL_ID` filtering precedes state creation.

- [x] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: add setup and testing guide"
```
