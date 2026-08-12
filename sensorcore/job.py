"""Run orchestration shared by every collector: read, write, publish metrics.

Deliberately stdlib-only. The sensor, sink and metrics publisher are injected,
so the whole control flow -- including both failure paths and the exit-code
contract the Prometheus alerts depend on -- is exercised in tests with fakes, on
any box, with no Bluetooth adapter, no weather gateway and no InfluxDB.

Adapters describe themselves through two optional attributes, so this module
needs no knowledge of what it is driving:

    retryable_errors  which exceptions are worth another attempt
    description       what to call the operation in a log line
"""

import time
from dataclasses import dataclass

from .exit_codes import EXIT_OK, EXIT_SENSOR_READ_FAILED, EXIT_SINK_WRITE_FAILED
from .retry import RetryExhausted, retry_call
from .textfile import RunMetrics

# Adapters declare their own transient failures via a `retryable_errors`
# attribute; this is the fallback for anything that does not.
DEFAULT_RETRYABLE_ERRORS = (Exception,)

DEFAULT_SENSOR_DESCRIPTION = "read the sensor"
DEFAULT_SINK_DESCRIPTION = "write to InfluxDB"

__all__ = ["RunOutcome", "run"]


@dataclass(frozen=True)
class RunOutcome:
    exit_code: int
    payload: object | None
    duration_seconds: float


def _retryable(component):
    return getattr(component, "retryable_errors", DEFAULT_RETRYABLE_ERRORS)


def _describe(component, default):
    return getattr(component, "description", default)


def run(config, sensor, sink, publisher, *, now=time.time, sleep=time.sleep, logger=None):
    """Execute one collection run. Always publishes metrics, never raises.

    Silence is the one outcome that must never happen: a run that dies without
    writing its metrics file looks exactly like a healthy job whose values
    simply have not changed.
    """
    started_at = now()
    payload = None
    exit_code = EXIT_OK

    try:
        payload = retry_call(
            sensor.read,
            attempts=config.max_retries,
            delay_seconds=config.retry_delay_seconds,
            retry_on=_retryable(sensor),
            description=_describe(sensor, DEFAULT_SENSOR_DESCRIPTION),
            logger=logger,
            sleep=sleep,
        )
    except RetryExhausted:
        exit_code = EXIT_SENSOR_READ_FAILED
        if logger is not None:
            logger.error("Sensor read failed after %d attempts", config.max_retries)
    else:
        try:
            retry_call(
                lambda: sink.write(payload),
                attempts=config.max_retries,
                delay_seconds=config.retry_delay_seconds,
                retry_on=_retryable(sink),
                description=_describe(sink, DEFAULT_SINK_DESCRIPTION),
                logger=logger,
                sleep=sleep,
            )
        except RetryExhausted:
            exit_code = EXIT_SINK_WRITE_FAILED
            if logger is not None:
                logger.error("InfluxDB write failed after %d attempts", config.max_retries)

    finished_at = now()
    outcome = RunOutcome(
        exit_code=exit_code,
        payload=payload,
        duration_seconds=finished_at - started_at,
    )

    publisher.publish(
        RunMetrics(
            exit_code=outcome.exit_code,
            duration_seconds=outcome.duration_seconds,
            payload=outcome.payload,
        ),
        config.textfile_dir,
        now=finished_at,
    )

    return outcome
