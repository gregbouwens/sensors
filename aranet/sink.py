"""InfluxDB write path.

The point schema here is a data-continuity contract with roughly a year of
existing aranet4_readings points -- measurement name, tag keys, field keys AND
field types are all load-bearing. tests/test_sink.py pins the exact line
protocol against ground truth captured from the pre-refactor implementation.
"""

import datetime

import urllib3.exceptions
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.exceptions import InfluxDBError
from influxdb_client.client.write_api import SYNCHRONOUS

MEASUREMENT = "aranet4_readings"

TAG_DEVICE = "device"
TAG_LOCATION = "location"
TAG_MAC_ADDRESS = "mac_address"

FIELD_CO2 = "co2"
FIELD_TEMPERATURE_F = "temperature_f"
FIELD_HUMIDITY = "humidity"
FIELD_PRESSURE = "pressure"
FIELD_BATTERY = "battery"

# Transient faults worth another attempt. urllib3.exceptions.HTTPError is the
# base of both NewConnectionError (DNS failure) and MaxRetryError -- the exact
# class of error that took out nine consecutive runs on 2026-08-03 while the
# office trunk cable was being re-terminated, because the old code re-raised it
# instead of retrying. A ValueError from bad config is deliberately NOT here.
INFLUX_RETRYABLE_ERRORS = (InfluxDBError, urllib3.exceptions.HTTPError, OSError)


def build_point(reading, *, device_name, location, mac_address, timestamp):
    """Build the InfluxDB point for a reading.

    int() / float() casts are not cosmetic: InfluxDB pins a field's type on
    first write and rejects a later write of a different type, so co2, humidity
    and battery must stay integers forever.
    """
    return (
        Point(MEASUREMENT)
        .tag(TAG_DEVICE, device_name)
        .tag(TAG_LOCATION, location)
        .tag(TAG_MAC_ADDRESS, mac_address)
        .field(FIELD_CO2, int(reading.co2_ppm))
        .field(FIELD_TEMPERATURE_F, float(reading.temperature_f))
        .field(FIELD_HUMIDITY, int(reading.humidity_percent))
        .field(FIELD_PRESSURE, float(reading.pressure_hpa))
        .field(FIELD_BATTERY, int(reading.battery_percent))
        .time(timestamp)
    )


class InfluxSink:
    """Writes readings to InfluxDB, one short-lived client per run."""

    retryable_errors = INFLUX_RETRYABLE_ERRORS

    def __init__(self, config):
        self._config = config

    @staticmethod
    def _now():
        # Timezone-aware UTC. The original used datetime.utcnow(), which returns
        # a NAIVE datetime and is deprecated from Python 3.12; the wire format
        # is identical, this just does not break on a future interpreter.
        return datetime.datetime.now(datetime.timezone.utc)

    def write(self, reading):
        point = build_point(
            reading,
            device_name=self._config.device_name,
            location=self._config.location,
            mac_address=self._config.aranet_mac,
            timestamp=self._now(),
        )

        with InfluxDBClient(
            url=self._config.influx_url,
            token=self._config.influx_token,
            org=self._config.influx_org,
        ) as client:
            client.write_api(write_options=SYNCHRONOUS).write(
                bucket=self._config.influx_bucket,
                org=self._config.influx_org,
                record=point,
            )
