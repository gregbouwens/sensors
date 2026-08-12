"""Process exit codes, surfaced to Prometheus as aranet_run_exit_code.

The codes themselves are shared with every collector in this repo -- see
sensorcore/exit_codes.py for why the numbering is a contract with
observethis/config/alert_rules.yml.

EXIT_INFLUX_WRITE_FAILED is kept as the Aranet4-facing spelling of the generic
EXIT_SINK_WRITE_FAILED. Same number, and the alert annotations already say
"3=influx".
"""

from sensorcore.exit_codes import (
    EXIT_CONFIG_ERROR,
    EXIT_OK,
    EXIT_SENSOR_READ_FAILED,
    EXIT_SINK_WRITE_FAILED,
)

EXIT_INFLUX_WRITE_FAILED = EXIT_SINK_WRITE_FAILED

__all__ = [
    "EXIT_OK",
    "EXIT_CONFIG_ERROR",
    "EXIT_SENSOR_READ_FAILED",
    "EXIT_INFLUX_WRITE_FAILED",
]
