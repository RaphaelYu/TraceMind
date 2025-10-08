from __future__ import annotations
import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def with_timeout(coro: Awaitable[T], timeout_s: float | None) -> T:
    if timeout_s is None or timeout_s <= 0:
        return await coro
    return await asyncio.wait_for(coro, timeout=timeout_s)


def default_backoff(attempt: int) -> float:
    # attempt starts at 1
    base = 0.5 * (2 ** (attempt - 1))
    return min(base, 8.0)


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    is_retryable: Callable[[Exception], bool],
    backoff: Callable[[int], float] = default_backoff,
) -> T:
    attempt = 0
    while True:
        try:
            attempt += 1
            return await fn()
        except Exception as e:
            if attempt > max_retries or not is_retryable(e):
                raise
            await asyncio.sleep(backoff(attempt))
