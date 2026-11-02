import httpx
import pytest

from services.webhook_deliveries import (
    RETRY_DELAYS_SECONDS,
    describe_delivery_error,
    idempotency_key,
    run_with_retries,
)


class FakeAttempts:
    """Returns the scripted outcomes in order and records the next_delay it was given."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.next_delays = []

    async def __call__(self, next_delay):
        self.next_delays.append(next_delay)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeSleep:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)


@pytest.mark.asyncio
async def test_first_attempt_success_does_not_retry() -> None:
    attempts, sleep = FakeAttempts([True]), FakeSleep()

    assert await run_with_retries(attempts, (10, 30, 90), sleep) is True
    assert attempts.next_delays == [10]
    assert sleep.calls == []


@pytest.mark.asyncio
async def test_retries_with_backoff_until_success() -> None:
    attempts, sleep = FakeAttempts([False, False, True]), FakeSleep()

    assert await run_with_retries(attempts, (10, 30, 90), sleep) is True
    assert sleep.calls == [10, 30]
    assert attempts.next_delays == [10, 30, 90]


@pytest.mark.asyncio
async def test_gives_up_after_first_try_plus_three_retries() -> None:
    attempts, sleep = FakeAttempts([False, False, False, False]), FakeSleep()

    assert await run_with_retries(attempts, (10, 30, 90), sleep) is False
    assert sleep.calls == [10, 30, 90]
    # The last attempt is told there is no further retry, so it records no next_retry_at.
    assert attempts.next_delays == [10, 30, 90, None]


@pytest.mark.asyncio
async def test_attempt_that_raises_counts_as_failure_and_is_retried() -> None:
    attempts, sleep = FakeAttempts([RuntimeError("db down"), True]), FakeSleep()

    assert await run_with_retries(attempts, (10, 30, 90), sleep) is True
    assert sleep.calls == [10]


def test_default_schedule_is_10_30_90_seconds() -> None:
    assert RETRY_DELAYS_SECONDS == (10, 30, 90)


def test_idempotency_key_is_invoice_plus_event() -> None:
    assert idempotency_key("abc-123", "invoice.approved") == "abc-123:invoice.approved"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"exc": httpx.ConnectError("refused")}, "Could not connect to the receiver"),
        ({"exc": httpx.ReadTimeout("slow")}, "did not answer within 3 seconds"),
        ({"status_code": 404}, "404 Not Found"),
        ({"status_code": 401}, "Check its authentication settings"),
        ({"status_code": 503}, "internal error (HTTP 503)"),
        ({"status_code": 422}, "rejected the request (HTTP 422)"),
        ({"exc": ValueError("boom")}, "Unexpected error while sending: ValueError"),
    ],
)
def test_errors_are_explained_in_plain_english(kwargs, expected) -> None:
    assert expected in describe_delivery_error(**kwargs)
