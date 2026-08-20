import asyncio
import random

import pytest

from services.captcha_service import (
    AnswerStatus,
    CaptchaService,
    RequestStatus,
    StartStatus,
)


@pytest.fixture
def now() -> list[float]:
    return [1_000_000.0]


@pytest.fixture
def service(now: list[float]) -> CaptchaService:
    return CaptchaService(clock=lambda: now[0], rng=random.Random(12345))


def test_generated_questions_obey_arithmetic_and_option_invariants(
    service: CaptchaService,
) -> None:
    positions: set[int] = set()
    operations: set[str] = set()

    for _ in range(100):
        question = service.generate_question()
        positions.add(question.correct_index)
        operations.add(question.operation)

        assert 1 <= question.answer <= 20
        assert len(question.options) == len(set(question.options)) == 4
        assert question.options[question.correct_index] == question.answer
        assert all(1 <= option <= 20 for option in question.options)
        if question.operation == "-":
            assert question.left >= question.right
            assert question.left - question.right == question.answer
        else:
            assert question.left + question.right == question.answer

    assert positions == {0, 1, 2, 3}
    assert operations == {"+", "-"}


@pytest.mark.asyncio
async def test_duplicate_join_request_reuses_active_state(
    service: CaptchaService,
) -> None:
    first = await service.create_request(-1001, 42, 9001, 999_990.0)
    duplicate = await service.create_request(-1001, 42, 9001, 999_990.0)

    assert first.is_new is True
    assert duplicate.is_new is False
    assert duplicate.state.captcha_id == first.state.captcha_id


@pytest.mark.asyncio
async def test_start_rejects_wrong_opaque_id(service: CaptchaService) -> None:
    await service.create_request(-1001, 42, 9001, 999_990.0)

    result = await service.start(-1001, 42, "forged-id")

    assert result.status is StartStatus.INVALID


@pytest.mark.asyncio
async def test_start_rejects_expired_request(
    service: CaptchaService, now: list[float]
) -> None:
    created = await service.create_request(-1001, 42, 9001, 999_700.0)

    result = await service.start(-1001, 42, created.state.captcha_id)

    assert result.status is StartStatus.EXPIRED
    assert result.state is not None
    assert result.state.status is RequestStatus.EXPIRED


@pytest.mark.asyncio
async def test_answer_rejects_different_user(service: CaptchaService) -> None:
    created = await service.create_request(-1001, 42, 9001, 999_990.0)
    await service.start(-1001, 42, created.state.captcha_id)

    result = await service.answer(-1001, 99, created.state.captcha_id, 0)

    assert result.status is AnswerStatus.INVALID


@pytest.mark.asyncio
async def test_correct_answer_passes_only_once(service: CaptchaService) -> None:
    created = await service.create_request(-1001, 42, 9001, 999_990.0)
    started = await service.start(-1001, 42, created.state.captcha_id)
    assert started.question is not None

    first, duplicate = await asyncio.gather(
        service.answer(
            -1001, 42, created.state.captcha_id, started.question.correct_index
        ),
        service.answer(
            -1001, 42, created.state.captcha_id, started.question.correct_index
        ),
    )

    assert {first.status, duplicate.status} == {
        AnswerStatus.CORRECT,
        AnswerStatus.INVALID,
    }


@pytest.mark.asyncio
async def test_fifth_wrong_answer_exhausts_request(service: CaptchaService) -> None:
    created = await service.create_request(-1001, 42, 9001, 999_990.0)
    started = await service.start(-1001, 42, created.state.captcha_id)
    assert started.question is not None
    question = started.question

    for attempt in range(1, 5):
        wrong_index = next(
            index for index in range(4) if index != question.correct_index
        )
        result = await service.answer(
            -1001, 42, created.state.captcha_id, wrong_index
        )
        assert result.status is AnswerStatus.WRONG
        assert result.attempts == attempt
        assert result.question is not None
        question = result.question

    wrong_index = next(index for index in range(4) if index != question.correct_index)
    result = await service.answer(-1001, 42, created.state.captcha_id, wrong_index)

    assert result.status is AnswerStatus.EXHAUSTED
    assert result.attempts == 5


@pytest.mark.asyncio
async def test_discard_removes_state(service: CaptchaService) -> None:
    await service.create_request(-1001, 42, 9001, 999_990.0)

    await service.discard(-1001, 42)

    assert await service.get_state(-1001, 42) is None

