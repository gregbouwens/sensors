"""Tests for the InfluxDB sink.

The line-protocol assertion is a DATA-CONTINUITY GUARD. Nearly a year of
aranet4_readings points already exist in the homelab bucket; if a refactor
renames the measurement, a tag or a field -- or changes an int field to a float,
which InfluxDB rejects as a type conflict on an existing series -- the writes
either land somewhere new or start failing. The expected string below was
generated from the pre-refactor point construction, not written by hand.
"""

import datetime

import pytest
from urllib3.exceptions import NewConnectionError

from aranet.readings import Reading
from aranet.sink import INFLUX_RETRYABLE_ERRORS, InfluxSink, build_point

READING = Reading(
    co2_ppm=612, temperature_c=22.2, humidity_percent=54,
    pressure_hpa=1012.0, battery_percent=91,
)

TIMESTAMP = datetime.datetime(2026, 8, 4, 21, 20, 6, tzinfo=datetime.timezone.utc)

# Ground truth captured from the original implementation. Do not edit to make a
# test pass -- if this changes, the schema changed, and that is the bug.
EXPECTED_LINE_PROTOCOL = (
    "aranet4_readings,device=aranet4-office,location=office,"
    "mac_address=AA:BB:CC:DD:EE:FF "
    "battery=91i,co2=612i,humidity=54i,pressure=1012,temperature_f=71.96 "
    "1785878406000000000"
)


def test_point_schema_is_unchanged_by_the_refactor():
    point = build_point(
        READING,
        device_name="aranet4-office",
        location="office",
        mac_address="AA:BB:CC:DD:EE:FF",
        timestamp=TIMESTAMP,
    )

    assert point.to_line_protocol() == EXPECTED_LINE_PROTOCOL


def test_integer_fields_stay_integers():
    """InfluxDB rejects a float write to a field already typed as an integer."""
    line = build_point(
        READING, device_name="d", location="l", mac_address="m", timestamp=TIMESTAMP,
    ).to_line_protocol()

    for field in ("co2", "humidity", "battery"):
        assert f"{field}=" in line
        value = line.split(f"{field}=")[1].split(",")[0].split(" ")[0]
        assert value.endswith("i"), f"{field} must be written as an integer"


def test_timestamps_are_timezone_aware_utc():
    """The original used the deprecated naive utcnow(); aware UTC is equivalent
    on the wire and does not break under Python 3.12+."""
    sink = InfluxSink.__new__(InfluxSink)
    timestamp = sink._now()

    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset() == datetime.timedelta(0)


@pytest.mark.parametrize(
    "error",
    [NewConnectionError(None, "Failed to resolve 'docker20.dbmob.nl'"), OSError("refused")],
    ids=["dns-failure", "socket-error"],
)
def test_connection_failures_are_classified_retryable(error):
    """Regression guard for 2026-08-03 -- see tests/test_retry.py."""
    assert isinstance(error, INFLUX_RETRYABLE_ERRORS)


def test_a_config_error_is_not_classified_retryable():
    """A guard that catches everything is not a guard."""
    assert not isinstance(ValueError("bad bucket"), INFLUX_RETRYABLE_ERRORS)
