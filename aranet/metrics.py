"""node_exporter textfile-collector metrics for the Aranet4 logging job.

node_exporter reads every *.prom file in its textfile directory on each scrape,
so a cron job that rewrites one file per run becomes a first-class Prometheus
target without needing to be a long-running server. Same pattern as
paperless/scripts/vision-ocr.py.

Two invariants earn their tests:

* A FAILED run carries the previous success timestamp forward. Resetting it
  would re-arm the staleness alert on every failure, so a permanently broken
  job would never look stale -- the alert would never fire.
* A run that has NEVER succeeded omits the watermark entirely rather than
  writing 0, which would read as "last succeeded in 1970" and page the moment
  the collector is switched on.
"""

import os
import tempfile
from dataclasses import dataclass

from .exit_codes import EXIT_OK
from .readings import Reading

METRICS_FILENAME = "aranet.prom"
METRICS_FILE_MODE = 0o644  # node_exporter runs as its own service account

METRIC_RUN_TIMESTAMP = "aranet_run_last_timestamp_seconds"
METRIC_LAST_SUCCESS = "aranet_run_last_success_timestamp_seconds"
METRIC_RUN_EXIT_CODE = "aranet_run_exit_code"
METRIC_RUN_DURATION = "aranet_run_duration_seconds"
METRIC_SENSOR_READ_OK = "aranet_sensor_read_ok"
METRIC_INFLUX_WRITE_OK = "aranet_influx_write_ok"
METRIC_CO2 = "aranet_co2_ppm"
METRIC_TEMPERATURE_F = "aranet_temperature_fahrenheit"
METRIC_HUMIDITY = "aranet_humidity_percent"
METRIC_PRESSURE = "aranet_pressure_hpa"
METRIC_BATTERY = "aranet_battery_percent"

_HELP = {
    METRIC_RUN_TIMESTAMP: "Unix time the last collection run finished, success or failure.",
    METRIC_LAST_SUCCESS: "Unix time of the last run that reached InfluxDB successfully.",
    METRIC_RUN_EXIT_CODE: "Exit code of the last run (0 ok, 1 config, 2 sensor, 3 influx).",
    METRIC_RUN_DURATION: "Wall-clock seconds the last run took.",
    METRIC_SENSOR_READ_OK: "1 if the last run read the Aranet4 over BLE, 0 otherwise.",
    METRIC_INFLUX_WRITE_OK: "1 if the last run wrote to InfluxDB, 0 otherwise.",
    METRIC_CO2: "CO2 concentration in ppm from the last successful read.",
    METRIC_TEMPERATURE_F: "Temperature in degrees Fahrenheit from the last successful read.",
    METRIC_HUMIDITY: "Relative humidity percent from the last successful read.",
    METRIC_PRESSURE: "Barometric pressure in hPa from the last successful read.",
    METRIC_BATTERY: "Aranet4 battery percent from the last successful read.",
}


@dataclass(frozen=True)
class RunMetrics:
    exit_code: int
    duration_seconds: float
    reading: Reading | None

    @property
    def succeeded(self):
        return self.exit_code == EXIT_OK

    @property
    def sensor_read_ok(self):
        return self.reading is not None

    @property
    def influx_write_ok(self):
        return self.succeeded


def _format(value):
    """Render a value in Prometheus exposition format.

    Explicitly avoids scientific notation: %g would turn a unix timestamp into
    1.78577e+09 and throw away the seconds we alert on.
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _metric(name, value):
    return f"# HELP {name} {_HELP[name]}\n# TYPE {name} gauge\n{name} {_format(value)}\n"


def render(run, now, previous_success=None):
    """Render one run's metrics as Prometheus exposition text."""
    last_success = now if run.succeeded else previous_success

    lines = [
        _metric(METRIC_RUN_TIMESTAMP, now),
        _metric(METRIC_RUN_EXIT_CODE, run.exit_code),
        _metric(METRIC_RUN_DURATION, run.duration_seconds),
        _metric(METRIC_SENSOR_READ_OK, run.sensor_read_ok),
        _metric(METRIC_INFLUX_WRITE_OK, run.influx_write_ok),
    ]

    if last_success is not None:
        lines.append(_metric(METRIC_LAST_SUCCESS, last_success))

    # Reading gauges are emitted only when there IS a reading. Repeating the
    # last known values on a failed run would show a live-looking sensor trace
    # while the sensor is actually unreachable.
    if run.reading is not None:
        lines.extend(
            [
                _metric(METRIC_CO2, run.reading.co2_ppm),
                _metric(METRIC_TEMPERATURE_F, run.reading.temperature_f),
                _metric(METRIC_HUMIDITY, run.reading.humidity_percent),
                _metric(METRIC_PRESSURE, run.reading.pressure_hpa),
                _metric(METRIC_BATTERY, run.reading.battery_percent),
            ]
        )

    return "".join(lines)


def read_last_success(path):
    """Return the previous success watermark, or None if unavailable.

    Never raises: a missing, truncated or hand-edited file must not take the
    collection job down with it.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.startswith(METRIC_LAST_SUCCESS + " "):
                    continue
                try:
                    return float(line.split(" ", 1)[1])
                except (IndexError, ValueError):
                    return None
    except OSError:
        return None
    return None


def write(run, textfile_dir, now):
    """Atomically publish this run's metrics.

    No-op when the textfile directory is absent -- instrumentation must never
    break the job it instruments (e.g. running by hand on a box without
    node_exporter).
    """
    textfile_dir = str(textfile_dir)
    if not os.path.isdir(textfile_dir):
        return

    target = os.path.join(textfile_dir, METRICS_FILENAME)
    text = render(run, now, previous_success=read_last_success(target))

    handle, temp_path = tempfile.mkstemp(dir=textfile_dir, prefix=".aranet.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temp_path, METRICS_FILE_MODE)
        os.replace(temp_path, target)  # atomic; node_exporter never sees a torn file
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
