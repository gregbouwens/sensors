"""Tests for the run orchestration.

The job is exercised entirely through injected fakes -- no Bluetooth adapter and
no InfluxDB required -- which is the whole point of splitting the adapters out.
"""

import pytest

from aranet.config import Config
from aranet.job import (
    EXIT_INFLUX_WRITE_FAILED,
    EXIT_OK,
    EXIT_SENSOR_READ_FAILED,
    run,
)
from aranet.metrics import METRICS_FILENAME
from aranet.readings import Reading, ReadingError

READING = Reading(
    co2_ppm=612, temperature_c=22.2, humidity_percent=54,
    pressure_hpa=1012.0, battery_percent=91,
)


def make_config(tmp_path, **overrides):
    env = {
        "INFLUX_URL": "http://docker20.dbmob.nl:8086",
        "INFLUXDB_TOKEN": "a-token",
        "INFLUX_ORG": "homelab",
        "INFLUX_BUCKET": "homelab",
        "ARANET_MAC": "AA:BB:CC:DD:EE:FF",
        "DEVICE_NAME": "aranet4-office",
        "LOCATION": "office",
        "TEXTFILE_COLLECTOR_DIR": str(tmp_path),
        "RETRY_DELAY_SECONDS": "0",
        **overrides,
    }
    return Config.from_env(env)


class FakeSensor:
    def __init__(self, reading=READING, error=None):
        self._reading = reading
        self._error = error
        self.reads = 0

    def read(self):
        self.reads += 1
        if self._error is not None:
            raise self._error
        return self._reading


class FakeSink:
    def __init__(self, error=None):
        self._error = error
        self.written = []

    def write(self, reading):
        if self._error is not None:
            raise self._error
        self.written.append(reading)


def metrics_text(tmp_path):
    return (tmp_path / METRICS_FILENAME).read_text()


def test_a_successful_run_writes_the_reading_and_exits_zero(tmp_path):
    sensor, sink = FakeSensor(), FakeSink()

    outcome = run(make_config(tmp_path), sensor, sink, now=lambda: 1000.0, sleep=lambda s: None)

    assert outcome.exit_code == EXIT_OK
    assert sink.written == [READING]
    assert "aranet_run_exit_code 0" in metrics_text(tmp_path)
    assert "aranet_run_last_success_timestamp_seconds 1000" in metrics_text(tmp_path)


def test_a_sensor_failure_exits_two_and_never_touches_influxdb(tmp_path):
    sensor = FakeSensor(error=OSError("no BLE adapter"))
    sink = FakeSink()

    outcome = run(make_config(tmp_path), sensor, sink, now=lambda: 1000.0, sleep=lambda s: None)

    assert outcome.exit_code == EXIT_SENSOR_READ_FAILED
    assert sink.written == [], "a reading we never got must not be written"
    assert "aranet_sensor_read_ok 0" in metrics_text(tmp_path)
    assert "aranet_influx_write_ok 0" in metrics_text(tmp_path)


def test_an_influx_failure_exits_three_and_records_a_good_sensor_read(tmp_path):
    """The discriminating signal: which half of the pipeline actually broke."""
    sensor, sink = FakeSensor(), FakeSink(error=OSError("connection refused"))

    outcome = run(make_config(tmp_path), sensor, sink, now=lambda: 1000.0, sleep=lambda s: None)

    assert outcome.exit_code == EXIT_INFLUX_WRITE_FAILED
    text = metrics_text(tmp_path)
    assert "aranet_sensor_read_ok 1" in text
    assert "aranet_influx_write_ok 0" in text


def test_an_implausible_reading_is_retried_then_reported_as_a_sensor_failure(tmp_path):
    sensor = FakeSensor(error=ReadingError("co2 out of range"))
    sink = FakeSink()

    outcome = run(make_config(tmp_path), sensor, sink, now=lambda: 1000.0, sleep=lambda s: None)

    assert outcome.exit_code == EXIT_SENSOR_READ_FAILED
    assert sensor.reads == 3, "a partial BLE read is transient -- it should be retried"


def test_a_run_emits_metrics_even_when_everything_fails(tmp_path):
    """Silence is the one outcome that must never happen -- it looks like health."""
    sensor = FakeSensor(error=OSError("boom"))

    run(make_config(tmp_path), sensor, FakeSink(), now=lambda: 1000.0, sleep=lambda s: None)

    assert (tmp_path / METRICS_FILENAME).exists()
    assert "aranet_run_last_timestamp_seconds 1000" in metrics_text(tmp_path)


def test_run_duration_is_measured_from_the_injected_clock(tmp_path):
    ticks = iter([1000.0, 1004.5])
    sensor, sink = FakeSensor(), FakeSink()

    outcome = run(make_config(tmp_path), sensor, sink, now=lambda: next(ticks), sleep=lambda s: None)

    assert outcome.duration_seconds == pytest.approx(4.5)
    assert "aranet_run_duration_seconds 4.5" in metrics_text(tmp_path)
