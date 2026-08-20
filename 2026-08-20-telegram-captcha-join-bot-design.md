# Telegram CAPTCHA Join Bot — Design

## Goal

Build a production-ready first version of an aiogram 3.x bot that verifies a
pending private-channel join request with a short arithmetic CAPTCHA before it
approves the request.

## Telegram constraints

`ChatJoinRequest.user_chat_id` may be used to contact the applicant for five
minutes after the request, provided the request has not already been processed
and no other administrator has contacted the user. The application therefore
uses a conservative CAPTCHA lifetime of 4 minutes 30 seconds, measured from
the Telegram join-request timestamp. The bot requires the channel administrator
right `can_invite_users` to approve or decline requests.

On CAPTCHA expiry or after five wrong answers, the bot declines the pending
request and removes its state. If another administrator or the applicant has
already resolved the request, Telegram API errors are handled without crashing
and local state is removed.

## Architecture

The project uses aiogram polling and is split into thin Telegram handlers,
keyboard builders, configuration, and a framework-independent CAPTCHA service.
The service owns all mutable state and exposes operations that can later be
implemented on Redis without changing handler responsibilities.

Active state is keyed by `(chat_id, user_id)` and contains `user_chat_id`, an
opaque random CAPTCHA ID, creation and expiry times, attempt count, current
question, answer choices, correct choice index, and lifecycle status. Per-state
`asyncio.Lock` objects serialize callbacks so rapid clicks cannot approve twice.

Callback payloads contain only a short action prefix, opaque CAPTCHA ID, and
selected option index. They contain neither the correct numeric answer nor a
trusted channel/user ID. The server resolves all authority-sensitive values
from stored state and compares the callback sender with the stored applicant.

## Data flow

1. A `chat_join_request` handler ignores every chat except `CHANNEL_ID`.
2. The handler creates or refreshes exactly one pending state for the applicant
   and sends the greeting to `user_chat_id` with an opaque start button.
3. On the start callback, the bot validates callback ownership, active state,
   CAPTCHA ID, configured channel, and TTL, then generates an addition or
   subtraction question with four unique answers in randomized order.
4. On an answer callback, the same checks run while holding the applicant's
   lock. A wrong choice increments attempts. Attempts one through four replace
   the message with a new question. Attempt five declines the request, deletes
   state, and replaces the message with the terminal failure text.
5. A correct choice reserves the state for approval while still under the lock,
   calls `approveChatJoinRequest` once, removes state, and replaces the message
   with the success text. Old and duplicate callbacks then resolve to no active
   state and cannot call approve again.

If an expired callback is received, the handler declines the request when still
possible, clears state, and displays an expiry message. A background cleanup
task is unnecessary in version one: expiry is enforced on every operation, and
stale records can be opportunistically purged by the service.

## CAPTCHA generation

Questions use addition or subtraction. Operands are generated so results are
integers from 1 through 20 and subtraction is never negative. Three distinct
plausible wrong answers in the same range are combined with the correct answer
and shuffled. The correct option is stored only in service state.

## Error handling and logging

Telegram API calls catch `TelegramBadRequest`, `TelegramForbiddenError`, and
the broader `TelegramAPIError` fallback. Errors are logged with chat and user
context; polling remains alive. A failure to send the initial message causes the
bot to remove state and attempt to decline the request, because the applicant
cannot complete the flow. A failed approve/decline also removes local state to
prevent unsafe retries from stale buttons.

Logs cover receipt, CAPTCHA delivery/start, wrong attempts, success, approval,
decline, expiry, and Telegram errors. Secrets are never logged.

## Configuration and operation

`BOT_TOKEN` and signed integer `CHANNEL_ID` are loaded from `.env` and validated
at startup. The bot requests only `chat_join_request` and `callback_query`
updates. README documents BotFather setup, the `can_invite_users` permission,
creation of an invite link with join-request approval enabled, channel ID
discovery, installation, startup, manual testing, the five-minute Telegram
window, and loss of RAM state after restart.

## Tests

Unit tests cover arithmetic invariants, four unique choices, randomized correct
position compatibility, duplicate-state behavior, ownership and opaque-ID
validation, TTL expiry, five-attempt cutoff, stale callbacks, and concurrent
answer serialization. Handler tests use mocked bot methods to prove that only a
valid correct answer calls approve and wrong answers never do. Import and compile
checks plus the full pytest suite provide final verification.

