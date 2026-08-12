"""node_exporter textfile metrics for the Ecowitt soil collector.

The generic half -- run health, the atomic write, the carry-forward invariants
-- lives in sensorcore.textfile. What is here is the Ecowitt's own gauges, and
one structural difference from the Aranet4: this collector reports N probes, so
its gauges carry `channel` and `plant` labels.

The metric that matters most is `ecowitt_channel_reporting`. It is emitted for
every EXPECTED channel, 1 when the probe answered and 0 when it did not, which
is what turns "this probe went silent" into something Prometheus can alert on.
Without it a flat battery is indistinguishable from a healthy plant: the gauges
for that channel would simply stop being written, and a metric that is absent
never fires a threshold rule.
"""

from sensorcore import textfile
from sensorcore.textfile import Sample, TextfilePublisher

METRICS_FILENAME = "ecowitt.prom"
METRIC_PREFIX = "ecowitt"

LABEL_CHANNEL = "channel"
LABEL_PLANT = "plant"

SUFFIX_CHANNEL_REPORTING = "channel_reporting"
SUFFIX_MOISTURE = "soil_moisture_percent"
SUFFIX_SOIL_TEMPERATURE_F = "soil_temperature_fahrenheit"
SUFFIX_EC = "soil_ec_microsiemens_per_cm"
SUFFIX_BATTERY_LEVEL = "battery_level"
SUFFIX_BATTERY_VOLTS = "battery_volts"
SUFFIX_AMBIENT_TEMPERATURE_F = "ambient_temperature_fahrenheit"
SUFFIX_AMBIENT_HUMIDITY = "ambient_humidity_percent"

METRIC_CHANNEL_REPORTING = f"{METRIC_PREFIX}_{SUFFIX_CHANNEL_REPORTING}"
METRIC_MOISTURE = f"{METRIC_PREFIX}_{SUFFIX_MOISTURE}"
METRIC_SOIL_TEMPERATURE_F = f"{METRIC_PREFIX}_{SUFFIX_SOIL_TEMPERATURE_F}"
METRIC_EC = f"{METRIC_PREFIX}_{SUFFIX_EC}"
METRIC_BATTERY_LEVEL = f"{METRIC_PREFIX}_{SUFFIX_BATTERY_LEVEL}"
METRIC_BATTERY_VOLTS = f"{METRIC_PREFIX}_{SUFFIX_BATTERY_VOLTS}"
METRIC_RUN_EXIT_CODE = f"{METRIC_PREFIX}_{textfile.SUFFIX_RUN_EXIT_CODE}"
METRIC_LAST_SUCCESS = f"{METRIC_PREFIX}_{textfile.SUFFIX_LAST_SUCCESS}"

HELP_CHANNEL_REPORTING = (
    "1 if this soil probe reported in the last run, 0 if it was expected but silent."
)
HELP_MOISTURE = "Soil moisture percent from the last successful read."
HELP_SOIL_TEMPERATURE_F = "Soil temperature in degrees Fahrenheit from the last successful read."
HELP_EC = "Soil electrical conductivity in uS/cm from the last successful read."
HELP_BATTERY_LEVEL = "Soil probe battery level, 0-5 (not a percentage)."
HELP_BATTERY_VOLTS = "Soil probe battery voltage from the last successful read."
HELP_AMBIENT_TEMPERATURE_F = "Gateway ambient temperature in degrees Fahrenheit."
HELP_AMBIENT_HUMIDITY = "Gateway ambient relative humidity percent."


def _labels(channel, plant):
    return {LABEL_CHANNEL: str(channel), LABEL_PLANT: plant}


def snapshot_samples(snapshot):
    """Gauges for one poll of the gateway."""
    samples = []

    # Emitted for every EXPECTED channel, reporting or not. This is the series
    # an alert can watch; the reading gauges below only exist when there IS a
    # reading, and an absent series never fires a rule.
    for channel in snapshot.expected_channels:
        samples.append(
            Sample(
                SUFFIX_CHANNEL_REPORTING,
                snapshot.is_reporting(channel),
                HELP_CHANNEL_REPORTING,
                _labels(channel, snapshot.plant_for(channel)),
            )
        )

    for reading in snapshot.channels:
        labels = _labels(reading.channel, reading.plant)
        samples.extend(
            [
                Sample(SUFFIX_MOISTURE, reading.moisture_percent, HELP_MOISTURE, labels),
                Sample(
                    SUFFIX_SOIL_TEMPERATURE_F,
                    reading.temperature_f,
                    HELP_SOIL_TEMPERATURE_F,
                    labels,
                ),
                Sample(SUFFIX_EC, reading.ec_microsiemens_per_cm, HELP_EC, labels),
                Sample(
                    SUFFIX_BATTERY_LEVEL,
                    reading.battery_level,
                    HELP_BATTERY_LEVEL,
                    labels,
                ),
                Sample(
                    SUFFIX_BATTERY_VOLTS,
                    reading.battery_volts,
                    HELP_BATTERY_VOLTS,
                    labels,
                ),
            ]
        )

    if snapshot.ambient is not None:
        samples.extend(
            [
                Sample(
                    SUFFIX_AMBIENT_TEMPERATURE_F,
                    snapshot.ambient.temperature_f,
                    HELP_AMBIENT_TEMPERATURE_F,
                ),
                Sample(
                    SUFFIX_AMBIENT_HUMIDITY,
                    snapshot.ambient.humidity_percent,
                    HELP_AMBIENT_HUMIDITY,
                ),
            ]
        )

    return samples


PUBLISHER = TextfilePublisher(
    prefix=METRIC_PREFIX,
    filename=METRICS_FILENAME,
    payload_samples=snapshot_samples,
    run_help={
        textfile.SUFFIX_SENSOR_READ_OK: (
            "1 if the last run reached the Ecowitt gateway over HTTP, 0 otherwise."
        )
    },
)
