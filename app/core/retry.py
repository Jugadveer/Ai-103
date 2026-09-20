"""
Retry with exponential backoff for Azure calls.

Transient network blips are the single most likely cause of a failed demo,
so every outbound call goes through here.
"""
import time
from typing import Callable, TypeVar

from app.core import logging as log

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    attempts: int = 3,
    base_delay: float = 0.5,
    label: str = "call",
) -> T:
    """Run fn(), retrying on exception. Re-raises the last error."""
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if attempt == attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            log.warn("retry", label=label, attempt=attempt, wait=delay,
                     error=str(exc)[:120])
            time.sleep(delay)
    log.error("retry_exhausted", label=label, attempts=attempts,
              error=str(last)[:200])
    raise last  # type: ignore[misc]
