from __future__ import annotations

import asyncio
import random
import secrets
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable


class RequestStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PASSED = "passed"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"


class StartStatus(StrEnum):
    READY = "ready"
    EXPIRED = "expired"
    INVALID = "invalid"


class AnswerStatus(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class CaptchaQuestion:
    left: int
    operation: str
    right: int
    answer: int
    options: tuple[int, int, int, int]
    correct_index: int

    @property
    def expression(self) -> str:
        return f"{self.left} {self.operation} {self.right}"


@dataclass(slots=True)
class CaptchaState:
    chat_id: int
    user_id: int
    user_chat_id: int
    captcha_id: str
    created_at: float
    expires_at: float
    attempts: int = 0
    question: CaptchaQuestion | None = None
    status: RequestStatus = RequestStatus.PENDING
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


@dataclass(frozen=True, slots=True)
class CreateRequestResult:
    state: CaptchaState
    is_new: bool


@dataclass(frozen=True, slots=True)
class StartResult:
    status: StartStatus
    state: CaptchaState | None = None
    question: CaptchaQuestion | None = None


@dataclass(frozen=True, slots=True)
class AnswerResult:
    status: AnswerStatus
    state: CaptchaState | None = None
    question: CaptchaQuestion | None = None
    attempts: int = 0


class CaptchaService:
    """Owns active CAPTCHA state independently from the Telegram framework."""

    def __init__(
        self,
        ttl_seconds: int = 270,
        max_attempts: int = 5,
        clock: Callable[[], float] = time.time,
        rng: random.Random | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_attempts = max_attempts
        self._clock = clock
        self._rng = rng or secrets.SystemRandom()
        self._states: dict[tuple[int, int], CaptchaState] = {}

    @staticmethod
    def _new_captcha_id() -> str:
        return secrets.token_urlsafe(9)

    def generate_question(self) -> CaptchaQuestion:
        operation = self._rng.choice(("+", "-"))
        if operation == "+":
            answer = self._rng.randint(2, 20)
            left = self._rng.randint(1, answer - 1)
            right = answer - left
        else:
            left = self._rng.randint(2, 20)
            right = self._rng.randint(1, left - 1)
            answer = left - right

        wrong_answers = self._rng.sample(
            [candidate for candidate in range(1, 21) if candidate != answer], 3
        )
        options = [answer, *wrong_answers]
        self._rng.shuffle(options)
        frozen_options = tuple(options)
        return CaptchaQuestion(
            left=left,
            operation=operation,
            right=right,
            answer=answer,
            options=frozen_options,  # type: ignore[arg-type]
            correct_index=frozen_options.index(answer),
        )

    async def create_request(
        self,
        chat_id: int,
        user_id: int,
        user_chat_id: int,
        request_timestamp: float,
    ) -> CreateRequestResult:
        key = (chat_id, user_id)
        existing = self._states.get(key)
        if (
            existing is not None
            and existing.expires_at > self._clock()
            and existing.status in {RequestStatus.PENDING, RequestStatus.ACTIVE}
        ):
            return CreateRequestResult(state=existing, is_new=False)

        state = CaptchaState(
            chat_id=chat_id,
            user_id=user_id,
            user_chat_id=user_chat_id,
            captcha_id=self._new_captcha_id(),
            created_at=request_timestamp,
            expires_at=request_timestamp + self._ttl_seconds,
        )
        self._states[key] = state
        return CreateRequestResult(state=state, is_new=True)

    async def get_state(self, chat_id: int, user_id: int) -> CaptchaState | None:
        return self._states.get((chat_id, user_id))

    async def start(
        self, chat_id: int, user_id: int, captcha_id: str
    ) -> StartResult:
        key = (chat_id, user_id)
        state = self._states.get(key)
        if state is None:
            return StartResult(StartStatus.INVALID)

        async with state.lock:
            if self._states.get(key) is not state:
                return StartResult(StartStatus.INVALID)
            if state.captcha_id != captcha_id or state.status is not RequestStatus.PENDING:
                return StartResult(StartStatus.INVALID)
            if self._clock() >= state.expires_at:
                state.status = RequestStatus.EXPIRED
                return StartResult(StartStatus.EXPIRED, state=state)

            state.question = self.generate_question()
            state.captcha_id = self._new_captcha_id()
            state.status = RequestStatus.ACTIVE
            return StartResult(StartStatus.READY, state=state, question=state.question)

    async def answer(
        self,
        chat_id: int,
        user_id: int,
        captcha_id: str,
        option_index: int,
    ) -> AnswerResult:
        key = (chat_id, user_id)
        state = self._states.get(key)
        if state is None:
            return AnswerResult(AnswerStatus.INVALID)

        async with state.lock:
            if self._states.get(key) is not state:
                return AnswerResult(AnswerStatus.INVALID)
            if (
                state.captcha_id != captcha_id
                or state.status is not RequestStatus.ACTIVE
                or state.question is None
                or option_index not in range(len(state.question.options))
            ):
                return AnswerResult(AnswerStatus.INVALID)
            if self._clock() >= state.expires_at:
                state.status = RequestStatus.EXPIRED
                return AnswerResult(
                    AnswerStatus.EXPIRED, state=state, attempts=state.attempts
                )
            if option_index == state.question.correct_index:
                state.status = RequestStatus.PASSED
                return AnswerResult(
                    AnswerStatus.CORRECT,
                    state=state,
                    question=state.question,
                    attempts=state.attempts,
                )

            state.attempts += 1
            if state.attempts >= self._max_attempts:
                state.status = RequestStatus.EXHAUSTED
                return AnswerResult(
                    AnswerStatus.EXHAUSTED, state=state, attempts=state.attempts
                )

            state.question = self.generate_question()
            state.captcha_id = self._new_captcha_id()
            return AnswerResult(
                AnswerStatus.WRONG,
                state=state,
                question=state.question,
                attempts=state.attempts,
            )

    async def discard(
        self, chat_id: int, user_id: int, captcha_id: str | None = None
    ) -> bool:
        key = (chat_id, user_id)
        state = self._states.get(key)
        if state is None:
            return False

        async with state.lock:
            if self._states.get(key) is not state:
                return False
            if captcha_id is not None and state.captcha_id != captcha_id:
                return False
            del self._states[key]
            return True

