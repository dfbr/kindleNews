from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    retries: int,
    retry_on: tuple[type[BaseException], ...],
    base_delay_seconds: float = 1.0,
) -> T:
    attempts = retries + 1
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retry_on as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(base_delay_seconds * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry_call exhausted without returning or raising")
