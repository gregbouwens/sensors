"""node_exporter textfile metrics for the Aranet4 job.

The generic half -- run-health metrics, the atomic write, and the two
carry-forward invariants -- lives in sensorcore.textfile and is shared with
every other collector. What remains here is only what is specific to the
Aranet4: which gauges it publishes and what they are called.

The metric NAMES are a contract with observethis' alert rules and with roughly
a year of Prometheus history. They are unchanged from the original single-file
implementation and must stay that way.
"""

from sensorcore import textfile
from sensorcore.textfile import Sample, TextfilePublisher

from .readings import Reading


class RunMetrics(textfile.RunMetrics):
    """The Aranet4 spelling of sensorcore's RunMetrics.

    The core calls what a collector read a `payload`, because for the Ecowitt
    gateway it is a multi-channel snapshot rather than one value object. Here
    it is a single Reading, and saying so keeps the entrypoint and the tests in
    the Aranet4's own vocabulary.
    """

    def __init__(self, *, exit_code, duration_seconds, reading):
        super().__init__(
            exit_code=exit_code, duration_seconds=duration_seconds, payload=reading
        )

    @property
    def reading(self):
        return self.payload

METRICS_FILENAME = "aranet.prom"
METRIC_PREFIX = "aranet"

SUFFIX_CO2 = "co2_ppm"
SUFFIX_TEMPERATURE_F = "temperature_fahrenheit"
SUFFIX_HUMIDITY = "humidity_percent"
SUFFIX_PRESSURE = "pressure_hpa"
SUFFIX_BATTERY = "battery_percent"

# Fully-qualified names, kept as module constants because the alert rules and
# the tests refer to them by their real Prometheus names.
METRIC_RUN_TIMESTAMP = f"{METRIC_PREFIX}_{textfile.SUFFIX_RUN_TIMESTAMP}"
METRIC_LAST_SUCCESS = f"{METRIC_PREFIX}_{textfile.SUFFIX_LAST_SUCCESS}"
METRIC_RUN_EXIT_CODE = f"{METRIC_PREFIX}_{textfile.SUFFIX_RUN_EXIT_CODE}"
METRIC_RUN_DURATION = f"{METRIC_PREFIX}_{textfile.SUFFIX_RUN_DURATION}"
METRIC_SENSOR_READ_OK = f"{METRIC_PREFIX}_{textfile.SUFFIX_SENSOR_READ_OK}"
METRIC_INFLUX_WRITE_OK = f"{METRIC_PREFIX}_{textfile.SUFFIX_INFLUX_WRITE_OK}"
METRIC_CO2 = f"{METRIC_PREFIX}_{SUFFIX_CO2}"
METRIC_TEMPERATURE_F = f"{METRIC_PREFIX}_{SUFFIX_TEMPERATURE_F}"
METRIC_HUMIDITY = f"{METRIC_PREFIX}_{SUFFIX_HUMIDITY}"
METRIC_PRESSURE = f"{METRIC_PREFIX}_{SUFFIX_PRESSURE}"
METRIC_BATTERY = f"{METRIC_PREFIX}_{SUFFIX_BATTERY}"


def reading_samples(reading: Reading):
    """The Aranet4's own gauges from one successful read."""
    return [
        Sample(SUFFIX_CO2, reading.co2_ppm, "CO2 concentration in ppm from the last successful read."),
        Sample(
            SUFFIX_TEMPERATURE_F,
            reading.temperature_f,
            "Temperature in degrees Fahrenheit from the last successful read.",
        ),
        Sample(
            SUFFIX_HUMIDITY,
            reading.humidity_percent,
            "Relative humidity percent from the last successful read.",
        ),
        Sample(
            SUFFIX_PRESSURE,
            reading.pressure_hpa,
            "Barometric pressure in hPa from the last successful read.",
        ),
        Sample(
            SUFFIX_BATTERY,
            reading.battery_percent,
            "Aranet4 battery percent from the last successful read.",
        ),
    ]


PUBLISHER = TextfilePublisher(
    prefix=METRIC_PREFIX,
    filename=METRICS_FILENAME,
    payload_samples=reading_samples,
    # Preserved verbatim from before the shared core was extracted: this string
    # is what a dashboard shows, and "over BLE" is the word that sends Greg to
    # the battery on his desk rather than to a container on docker20.
    run_help={
        textfile.SUFFIX_SENSOR_READ_OK: (
            "1 if the last run read the Aranet4 over BLE, 0 otherwise."
        )
    },
)


# Module-level wrappers. These keep the call sites (and the tests that pin the
# invariants) reading the same as before the shared core was extracted.


def render(run, now, previous_success=None):
    return PUBLISHER.render(run, now, previous_success=previous_success)


def read_last_success(path):
    return PUBLISHER.read_last_success(path)


def write(run, textfile_dir, now):
    return PUBLISHER.publish(run, textfile_dir, now)


__all__ = [
    "METRICS_FILENAME",
    "METRIC_RUN_TIMESTAMP",
    "METRIC_LAST_SUCCESS",
    "METRIC_RUN_EXIT_CODE",
    "METRIC_RUN_DURATION",
    "METRIC_SENSOR_READ_OK",
    "METRIC_INFLUX_WRITE_OK",
    "METRIC_CO2",
    "METRIC_TEMPERATURE_F",
    "METRIC_HUMIDITY",
    "METRIC_PRESSURE",
    "METRIC_BATTERY",
    "PUBLISHER",
    "RunMetrics",
    "read_last_success",
    "render",
    "write",
]
