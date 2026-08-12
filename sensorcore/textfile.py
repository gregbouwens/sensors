"""node_exporter textfile-collector publishing, shared by every collector.

node_exporter reads every *.prom file in its textfile directory on each scrape,
so a cron job that rewrites one file per run becomes a first-class Prometheus
target without needing to be a long-running server. Same pattern paperless uses
for `vision-ocr`.

Each collector supplies a metric PREFIX (`aranet`, `ecowitt`) and a function
that turns its payload into gauge samples. Everything else -- the run-health
metrics, the atomic write, and the two invariants below -- is identical across
collectors and therefore lives here and is tested once.

Two invariants earn their tests:

* A FAILED run carries the previous success timestamp forward. Resetting it
  would re-arm the staleness alert on every failure, so a permanently broken
  job would never look stale -- the alert would never fire.
* A run that has NEVER succeeded omits the watermark entirely rather than
  writing 0, which would read as "last succeeded in 1970" and page the moment
  the collector is switched on.

Metric names are `{prefix}_{suffix}`, which reproduces the names the aranet job
has been publishing for a year. Those names are a contract with observethis'
alert rules and with the existing Prometheus history -- renaming one silently
breaks an alert, so the suffixes below are append-only.
"""

import os
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Mapping

from .exit_codes import EXIT_OK

METRICS_FILE_MODE = 0o644  # node_exporter runs as its own service account

SUFFIX_RUN_TIMESTAMP = "run_last_timestamp_seconds"
SUFFIX_LAST_SUCCESS = "run_last_success_timestamp_seconds"
SUFFIX_RUN_EXIT_CODE = "run_exit_code"
SUFFIX_RUN_DURATION = "run_duration_seconds"
SUFFIX_SENSOR_READ_OK = "sensor_read_ok"
SUFFIX_INFLUX_WRITE_OK = "influx_write_ok"

_RUN_HELP = {
    SUFFIX_RUN_TIMESTAMP: "Unix time the last collection run finished, success or failure.",
    SUFFIX_LAST_SUCCESS: "Unix time of the last run that reached InfluxDB successfully.",
    SUFFIX_RUN_EXIT_CODE: "Exit code of the last run (0 ok, 1 config, 2 sensor, 3 influx).",
    SUFFIX_RUN_DURATION: "Wall-clock seconds the last run took.",
    SUFFIX_SENSOR_READ_OK: "1 if the last run read the sensor, 0 otherwise.",
    SUFFIX_INFLUX_WRITE_OK: "1 if the last run wrote to InfluxDB, 0 otherwise.",
}


@dataclass(frozen=True)
class Sample:
    """One Prometheus sample: a metric name suffix, a value, optional labels.

    `name` is the suffix only -- the publisher prepends its prefix -- so a
    collector cannot accidentally publish under another collector's namespace.
    """

    name: str
    value: float | int | bool
    help_text: str
    labels: Mapping[str, str] = field(default_factory=dict)


def format_value(value):
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


def format_labels(labels):
    """Render a label set, escaping per the Prometheus exposition spec.

    A plant nicknamed `Tracy's "big" fern` would otherwise emit a broken line
    and make node_exporter reject the WHOLE file -- taking the aranet metrics
    down with it, since they share a scrape.
    """
    if not labels:
        return ""
    parts = []
    for key in sorted(labels):
        escaped = (
            str(labels[key])
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )
        parts.append(f'{key}="{escaped}"')
    return "{" + ",".join(parts) + "}"


@dataclass(frozen=True)
class RunMetrics:
    """One run's outcome, plus whatever the collector read (or None).

    `payload` is deliberately untyped: for the Aranet4 it is a single Reading,
    for the Ecowitt gateway it is a multi-channel snapshot. Only the
    collector's own `payload_samples` ever looks inside it.
    """

    exit_code: int
    duration_seconds: float
    payload: object | None

    @property
    def succeeded(self):
        return self.exit_code == EXIT_OK

    @property
    def sensor_read_ok(self):
        return self.payload is not None

    @property
    def influx_write_ok(self):
        return self.succeeded


class TextfilePublisher:
    """Publishes one collector's run health and gauges to a .prom file.

    `payload_samples` maps a successful run's payload to domain gauges. It is
    only ever called when there IS a payload, so implementations never handle
    None.
    """

    def __init__(
        self,
        *,
        prefix: str,
        filename: str,
        payload_samples: Callable[[object], list],
        run_help: Mapping[str, str] | None = None,
    ):
        self._prefix = prefix
        self._filename = filename
        self._payload_samples = payload_samples
        # A collector may sharpen the generic run-metric HELP text -- "read the
        # Aranet4 over BLE" says more to whoever is reading a dashboard at 2am
        # than "read the sensor" does. Values only; the metric NAMES are fixed.
        self._run_help = {**_RUN_HELP, **(run_help or {})}

    @property
    def filename(self):
        return self._filename

    def qualify(self, suffix):
        """Full metric name for a suffix, e.g. 'soil_moisture_percent'."""
        return f"{self._prefix}_{suffix}"

    def _run_samples(self, run, now, last_success):
        help_for = self._run_help
        samples = [
            Sample(SUFFIX_RUN_TIMESTAMP, now, help_for[SUFFIX_RUN_TIMESTAMP]),
            Sample(SUFFIX_RUN_EXIT_CODE, run.exit_code, help_for[SUFFIX_RUN_EXIT_CODE]),
            Sample(SUFFIX_RUN_DURATION, run.duration_seconds, help_for[SUFFIX_RUN_DURATION]),
            Sample(SUFFIX_SENSOR_READ_OK, run.sensor_read_ok, help_for[SUFFIX_SENSOR_READ_OK]),
            Sample(SUFFIX_INFLUX_WRITE_OK, run.influx_write_ok, help_for[SUFFIX_INFLUX_WRITE_OK]),
        ]
        if last_success is not None:
            samples.append(
                Sample(SUFFIX_LAST_SUCCESS, last_success, help_for[SUFFIX_LAST_SUCCESS])
            )
        return samples

    def render(self, run, now, previous_success=None):
        """Render one run's metrics as Prometheus exposition text."""
        last_success = now if run.succeeded else previous_success
        samples = self._run_samples(run, now, last_success)

        # Gauges are emitted only when there IS a payload. Repeating the last
        # known values on a failed run would show a live-looking sensor trace
        # while the sensor is actually unreachable.
        if run.payload is not None:
            samples.extend(self._payload_samples(run.payload))

        return self._render_samples(samples)

    def _render_samples(self, samples):
        # HELP/TYPE are emitted once per metric NAME, not once per sample. A
        # repeated HELP line makes node_exporter reject the entire file, which
        # is how a per-channel metric would take the whole scrape down.
        declared = set()
        lines = []
        for sample in samples:
            name = self.qualify(sample.name)
            if name not in declared:
                declared.add(name)
                lines.append(f"# HELP {name} {sample.help_text}\n")
                lines.append(f"# TYPE {name} gauge\n")
            labels = format_labels(sample.labels)
            lines.append(f"{name}{labels} {format_value(sample.value)}\n")
        return "".join(lines)

    def read_last_success(self, path):
        """Return the previous success watermark, or None if unavailable.

        Never raises: a missing, truncated or hand-edited file must not take the
        collection job down with it.
        """
        wanted = self.qualify(SUFFIX_LAST_SUCCESS) + " "
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.startswith(wanted):
                        continue
                    try:
                        return float(line.split(" ", 1)[1])
                    except (IndexError, ValueError):
                        return None
        except OSError:
            return None
        return None

    def publish(self, run, textfile_dir, now):
        """Atomically publish this run's metrics.

        No-op when the textfile directory is absent -- instrumentation must
        never break the job it instruments (e.g. running by hand on a box
        without node_exporter).
        """
        textfile_dir = str(textfile_dir)
        if not os.path.isdir(textfile_dir):
            return

        target = os.path.join(textfile_dir, self._filename)
        text = self.render(run, now, previous_success=self.read_last_success(target))

        handle, temp_path = tempfile.mkstemp(
            dir=textfile_dir, prefix=f".{self._prefix}.", suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.chmod(temp_path, METRICS_FILE_MODE)
            os.replace(temp_path, target)  # atomic; node_exporter never sees a torn file
        except BaseException:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
