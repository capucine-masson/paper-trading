"""Bounded retries with an increasing delay, for transient errors only."""

import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500


def is_transient_status(status: int) -> bool:
    return status == HTTP_TOO_MANY_REQUESTS or status >= HTTP_SERVER_ERROR


def retry[T](
    action: Callable[[], T],
    catch: tuple[type[Exception], ...],
    is_transient: Callable[[Exception], bool],
    max_attempts: int,
    delay_s: float,
) -> T:
    """Run the action; a caught error that is not transient, or the last one, is raised as is."""
    attempt = 1
    while True:
        try:
            return action()
        except catch as error:
            if not is_transient(error) or attempt >= max_attempts:
                raise
            logger.warning(
                "transient %s (attempt %d/%d), retrying in %.1fs",
                type(error).__name__,
                attempt,
                max_attempts,
                delay_s,
            )
            time.sleep(delay_s)
            delay_s *= 2
            attempt += 1
