"""Tests for the shared retry helper.

The regression that motivated this module: on 2026-08-03 the office switch was
disconnected for 45 minutes while the trunk cat6 was re-terminated. Every
InfluxDB write raised a urllib3 connection error, which the old code caught in a
generic `except Exception: raise` branch placed AFTER the InfluxDBError retry
branch -- so DNS/connection failures were never retried at all. Nine consecutive
runs hard-failed instead of retrying.
"""

import pytest
from urllib3.exceptions import MaxRetryError, NewConnectionError

from sensorcore.retry import RetryExhausted, retry_call


class Recorder:
    """Records calls and sleeps so tests never actually wait."""

    def __init__(self):
        self.calls = 0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)


def test_retry_call_returns_value_without_retrying_when_operation_succeeds():
    rec = Recorder()

    def operation():
        rec.calls += 1
        return "reading"

    result = retry_call(
        operation,
        attempts=3,
        delay_seconds=5,
        retry_on=(OSError,),
        description="read sensor",
        sleep=rec.sleep,
    )

    assert result == "reading"
    assert rec.calls == 1
    assert rec.sleeps == []


def test_retry_call_recovers_after_transient_failures():
    rec = Recorder()

    def operation():
        rec.calls += 1
        if rec.calls < 3:
            raise OSError("transient")
        return "reading"

    result = retry_call(
        operation,
        attempts=3,
        delay_seconds=5,
        retry_on=(OSError,),
        description="read sensor",
        sleep=rec.sleep,
    )

    assert result == "reading"
    assert rec.calls == 3
    assert rec.sleeps == [5, 5], "should sleep between attempts, not after the last"


def test_retry_call_raises_retry_exhausted_chaining_the_last_error():
    rec = Recorder()
    final_error = OSError("still broken")

    def operation():
        rec.calls += 1
        raise final_error

    with pytest.raises(RetryExhausted) as excinfo:
        retry_call(
            operation,
            attempts=3,
            delay_seconds=5,
            retry_on=(OSError,),
            description="write to InfluxDB",
            sleep=rec.sleep,
        )

    assert rec.calls == 3
    assert rec.sleeps == [5, 5]
    assert excinfo.value.__cause__ is final_error
    assert "write to InfluxDB" in str(excinfo.value)


def test_retry_call_fails_fast_on_a_non_retryable_error():
    """Fail fast and explicitly -- a config error must not burn three attempts."""
    rec = Recorder()

    def operation():
        rec.calls += 1
        raise ValueError("INFLUX_BUCKET not set")

    with pytest.raises(ValueError, match="INFLUX_BUCKET not set"):
        retry_call(
            operation,
            attempts=3,
            delay_seconds=5,
            retry_on=(OSError,),
            description="write to InfluxDB",
            sleep=rec.sleep,
        )

    assert rec.calls == 1
    assert rec.sleeps == []


@pytest.mark.parametrize(
    "error",
    [
        NewConnectionError(None, "Failed to resolve 'docker20.dbmob.nl'"),
        MaxRetryError(None, "http://docker20.dbmob.nl:8086", reason=None),
    ],
    ids=["dns-resolution-failure", "max-retry-error"],
)
def test_connection_errors_are_retried(error):
    """Regression guard for the 2026-08-03 outage.

    Both of these urllib3 errors descend from HTTPError, which is what the
    InfluxDB sink registers as retryable. Before the fix they escaped the retry
    loop entirely and each run failed on the first attempt.
    """
    from aranet.sink import INFLUX_RETRYABLE_ERRORS

    rec = Recorder()

    def operation():
        rec.calls += 1
        if rec.calls == 1:
            raise error
        return "written"

    result = retry_call(
        operation,
        attempts=3,
        delay_seconds=1,
        retry_on=INFLUX_RETRYABLE_ERRORS,
        description="write to InfluxDB",
        sleep=rec.sleep,
    )

    assert result == "written"
    assert rec.calls == 2, "the connection error should have been retried, not re-raised"
