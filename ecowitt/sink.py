"""InfluxDB write path for the Ecowitt soil collector.

One poll produces N points -- one per reporting probe, plus one for the
gateway's ambient sensor -- written in a single batch so a partial write cannot
leave one plant recorded and another not.

Every point in a snapshot shares ONE timestamp, taken once. Letting each point
stamp itself would scatter a single poll across a few hundred milliseconds and
make "were these two pots read at the same moment?" unanswerable in a query.

As with the Aranet4 sink, the int()/float() casts are not cosmetic: InfluxDB
pins a field's type on first write and rejects a later write of a different
type, so moisture and battery_level must stay integers forever.
"""

import datetime
import time

import urllib3.exceptions
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.exceptions import InfluxDBError
from influxdb_client.client.write_api import SYNCHRONOUS

MEASUREMENT_SOIL = "ecowitt_soil_readings"
MEASUREMENT_AMBIENT = "ecowitt_ambient_readings"

TAG_DEVICE = "device"
TAG_LOCATION = "location"
TAG_CHANNEL = "channel"
TAG_PLANT = "plant"

FIELD_MOISTURE = "moisture"
FIELD_TEMPERATURE_F = "temperature_f"
FIELD_EC = "ec"
FIELD_BATTERY_LEVEL = "battery_level"
FIELD_BATTERY_VOLTS = "battery_volts"
FIELD_HUMIDITY = "humidity"

# Same set the Aranet4 sink retries on, and for the same reason: urllib3's
# HTTPError is the base of both NewConnectionError (DNS failure) and
# MaxRetryError, the exact class of fault that took out nine consecutive runs
# on 2026-08-03 while the office trunk cable was being re-terminated.
INFLUX_RETRYABLE_ERRORS = (InfluxDBError, urllib3.exceptions.HTTPError, OSError)


def build_points(snapshot, *, device_name, location, timestamp):
    """Build every point for one snapshot, all sharing a single timestamp."""
    points = []

    for reading in snapshot.channels:
        points.append(
            Point(MEASUREMENT_SOIL)
            .tag(TAG_DEVICE, device_name)
            .tag(TAG_LOCATION, location)
            .tag(TAG_CHANNEL, str(reading.channel))
            .tag(TAG_PLANT, reading.plant)
            .field(FIELD_MOISTURE, int(reading.moisture_percent))
            .field(FIELD_TEMPERATURE_F, float(reading.temperature_f))
            .field(FIELD_EC, float(reading.ec_microsiemens_per_cm))
            .field(FIELD_BATTERY_LEVEL, int(reading.battery_level))
            .field(FIELD_BATTERY_VOLTS, float(reading.battery_volts))
            .time(timestamp)
        )

    if snapshot.ambient is not None:
        points.append(
            Point(MEASUREMENT_AMBIENT)
            .tag(TAG_DEVICE, device_name)
            .tag(TAG_LOCATION, location)
            .field(FIELD_TEMPERATURE_F, float(snapshot.ambient.temperature_f))
            .field(FIELD_HUMIDITY, int(snapshot.ambient.humidity_percent))
            .time(timestamp)
        )

    return points


class InfluxSink:
    """Writes a snapshot to InfluxDB, one short-lived client per run."""

    retryable_errors = INFLUX_RETRYABLE_ERRORS
    description = "write to InfluxDB"

    def __init__(self, config):
        self._config = config

    @staticmethod
    def _timestamp_for(snapshot):
        """When the probes were READ, not when we got around to writing them.

        This is what makes a retry idempotent. On 2026-08-12 the very first
        write timed out client-side after 10s and was retried -- but InfluxDB
        had already accepted it, so stamping the retry with a fresh clock read
        turned one reading into two rows 15 seconds apart. Reusing the read
        timestamp means the retry overwrites the same point instead.
        """
        read_at = getattr(snapshot, "read_at", None)
        if read_at is None:
            read_at = time.time()
        return datetime.datetime.fromtimestamp(read_at, datetime.timezone.utc)

    def points_for(self, snapshot):
        """Every point for a snapshot. Deterministic: same input, same output."""
        return build_points(
            snapshot,
            device_name=self._config.device_name,
            location=self._config.location,
            timestamp=self._timestamp_for(snapshot),
        )

    def write(self, snapshot):
        points = self.points_for(snapshot)

        # A snapshot where every probe is silent is a legitimate outcome -- the
        # gateway answered, the probes did not. There is nothing to write, and
        # opening a client to write nothing would turn a probe problem into an
        # InfluxDB-shaped failure.
        if not points:
            return

        with InfluxDBClient(
            url=self._config.influx_url,
            token=self._config.influx_token,
            org=self._config.influx_org,
        ) as client:
            client.write_api(write_options=SYNCHRONOUS).write(
                bucket=self._config.influx_bucket,
                org=self._config.influx_org,
                record=points,
            )
