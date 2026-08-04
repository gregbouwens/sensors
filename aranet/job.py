"""Run orchestration: read the sensor, write it to InfluxDB, publish metrics.

Deliberately stdlib-only. The sensor and sink are injected, so the whole control
flow -- including both failure paths and the exit-code contract the Prometheus
alerts depend on -- is exercised in tests/test_job.py with fakes, on any box,
with no Bluetooth adapter and no InfluxDB.
"""

import time
from dataclasses import dataclass

from . import metrics
from .exit_codes import (
    EXIT_INFLUX_WRITE_FAILED,
    EXIT_OK,
    EXIT_SENSOR_READ_FAILED,
)
from .readings import Reading
from .retry import RetryExhausted, retry_call

# Adapters declare their own transient failures via a `retryable_errors`
# attribute; this is the fallback for anything that does not.
DEFAULT_RETRYABLE_ERRORS = (Exception,)

__all__ = [
    "EXIT_OK",
    "EXIT_SENSOR_READ_FAILED",
    "EXIT_INFLUX_WRITE_FAILED",
    "RunOutcome",
    "run",
]


@dataclass(frozen=True)
class RunOutcome:
    exit_code: int
    reading: Reading | None
    duration_seconds: float


def _retryable(component):
    return getattr(component, "retryable_errors", DEFAULT_RETRYABLE_ERRORS)


def run(config, sensor, sink, *, now=time.time, sleep=time.sleep, logger=None):
    """Execute one collection run. Always publishes metrics, never raises.

    Silence is the one outcome that must never happen: a run that dies without
    writing its metrics file looks exactly like a healthy job whose values
    simply have not changed.
    """
    started_at = now()
    reading = None
    exit_code = EXIT_OK

    try:
        reading = retry_call(
            sensor.read,
            attempts=config.max_retries,
            delay_seconds=config.retry_delay_seconds,
            retry_on=_retryable(sensor),
            description="read the Aranet4",
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
                lambda: sink.write(reading),
                attempts=config.max_retries,
                delay_seconds=config.retry_delay_seconds,
                retry_on=_retryable(sink),
                description="write to InfluxDB",
                logger=logger,
                sleep=sleep,
            )
        except RetryExhausted:
            exit_code = EXIT_INFLUX_WRITE_FAILED
            if logger is not None:
                logger.error("InfluxDB write failed after %d attempts", config.max_retries)

    finished_at = now()
    outcome = RunOutcome(
        exit_code=exit_code,
        reading=reading,
        duration_seconds=finished_at - started_at,
    )

    metrics.write(
        metrics.RunMetrics(
            exit_code=outcome.exit_code,
            duration_seconds=outcome.duration_seconds,
            reading=outcome.reading,
        ),
        config.textfile_dir,
        now=finished_at,
    )

    return outcome
