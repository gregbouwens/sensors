"""Aranet4 run orchestration.

The control flow lives in sensorcore.job and is shared with every collector.
This module binds it to the Aranet4's metrics publisher and re-exposes the
outcome under the name the entrypoint reads (`reading` rather than the generic
`payload`), so nothing above this line had to change when the core was
extracted.
"""

from dataclasses import dataclass

from sensorcore import job as core_job

from .exit_codes import (
    EXIT_INFLUX_WRITE_FAILED,
    EXIT_OK,
    EXIT_SENSOR_READ_FAILED,
)
from .metrics import PUBLISHER
from .readings import Reading

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


def run(config, sensor, sink, **kwargs):
    """Execute one Aranet4 collection run. Always publishes metrics."""
    outcome = core_job.run(config, sensor, sink, PUBLISHER, **kwargs)
    return RunOutcome(
        exit_code=outcome.exit_code,
        reading=outcome.payload,
        duration_seconds=outcome.duration_seconds,
    )
