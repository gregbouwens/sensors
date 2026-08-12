"""Retry helper shared by the sensor-read and InfluxDB-write paths.

Replaces two near-identical hand-rolled retry loops. The InfluxDB copy had a bug:
its `except InfluxDBError` retry branch was followed by a bare
`except Exception: raise`, so connection and DNS failures -- the single most
likely transient fault on a home network -- skipped the retry entirely. See
tests/test_retry.py for the regression guard.
"""

import time


class RetryExhausted(Exception):
    """Every attempt failed. The underlying error is chained as __cause__."""


def retry_call(
    operation,
    *,
    attempts,
    delay_seconds,
    retry_on,
    description,
    logger=None,
    sleep=time.sleep,
):
    """Call `operation`, retrying on `retry_on` exceptions.

    Anything not listed in `retry_on` propagates immediately -- a configuration
    error should fail fast, not burn three attempts and a fifteen-second delay.

    `sleep` is injectable so tests exercise the backoff without waiting.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retry_on as error:
            last_error = error
            if logger is not None:
                logger.warning(
                    "Attempt %d/%d to %s failed: %s", attempt, attempts, description, error
                )
            if attempt < attempts:
                if logger is not None:
                    logger.info("Retrying in %s seconds...", delay_seconds)
                sleep(delay_seconds)

    raise RetryExhausted(
        f"Failed to {description} after {attempts} attempts"
    ) from last_error
