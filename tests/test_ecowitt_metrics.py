"""Tests for the Ecowitt collector's Prometheus gauges and InfluxDB points.

The behaviour under test that the Aranet4 job has no equivalent of: N probes
per run, and the need to make a SILENT probe visible. A missing sensor that
merely stops emitting metrics cannot be alerted on -- an absent series never
crosses a threshold -- so `ecowitt_channel_reporting` is emitted for every
expected channel whether it answered or not.
"""

import json
import pathlib

import pytest

from ecowitt.metrics import (
    METRIC_CHANNEL_REPORTING,
    METRIC_MOISTURE,
    METRICS_FILENAME,
    PUBLISHER,
)
from ecowitt.readings import parse_livedata
from ecowitt.sink import (
    MEASUREMENT_AMBIENT,
    MEASUREMENT_SOIL,
    build_points,
)
from sensorcore.textfile import RunMetrics

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "livedata_two_soil_channels.json"

NAMES = {1: "Fiddle Leaf Fig", 2: "Monstera"}


def snapshot(payload=None, expected=(1, 2), names=NAMES):
    payload = payload if payload is not None else json.loads(FIXTURE.read_text())
    return parse_livedata(payload, expected_channels=expected, channel_names=names)


def channel_entry(number, **overrides):
    entry = {
        "channel": str(number),
        "name": "",
        "battery": "5",
        "voltage": "1.56",
        "humidity": "34%",
        "temp": "69.8",
        "unit": "F",
        "ec": "120 uS/cm",
    }
    entry.update(overrides)
    return entry


def render(snap, exit_code=0):
    return PUBLISHER.render(
        RunMetrics(exit_code=exit_code, duration_seconds=0.4, payload=snap), now=1000.0
    )


def samples(text, metric):
    """Every sample line for one metric name, as {labelstring: value}."""
    found = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(metric):
            continue
        head, _, raw = line.rpartition(" ")
        if head.split("{")[0] != metric:
            continue
        found[head[len(metric) :]] = float(raw)
    return found


# ── The invariant that makes a dead probe visible ───────────────────────────


def test_a_silent_probe_reports_zero_rather_than_vanishing():
    """THE alert-critical behaviour of this collector.

    Channel 2's battery dies, so the gateway stops listing it. If the collector
    only published what it received, channel 2's series would simply stop
    updating -- and a rule like `moisture < 20` can never fire on a series that
    is not there. The plant would go dry in silence.
    """
    text = render(snapshot(payload={"ch_ec": [channel_entry(1)]}, expected=(1, 2)))

    reporting = samples(text, METRIC_CHANNEL_REPORTING)
    assert reporting['{channel="1",plant="Fiddle Leaf Fig"}'] == 1
    assert reporting['{channel="2",plant="Monstera"}'] == 0


def test_a_silent_probe_is_still_named_after_its_plant():
    """'Monstera has stopped reporting' beats 'channel 2 has stopped reporting'."""
    text = render(snapshot(payload={"ch_ec": []}, expected=(2,), names={2: "Monstera"}))

    assert '{channel="2",plant="Monstera"} 0' in text


def test_a_silent_probe_publishes_no_stale_reading_gauges():
    """Carrying the last known moisture forward would show a thriving plant."""
    text = render(snapshot(payload={"ch_ec": [channel_entry(1)]}, expected=(1, 2)))

    moisture = samples(text, METRIC_MOISTURE)
    assert '{channel="1",plant="Fiddle Leaf Fig"}' in moisture
    assert '{channel="2",plant="Monstera"}' not in moisture


def test_every_expected_channel_reports_even_when_all_are_silent():
    text = render(snapshot(payload={"ch_ec": []}, expected=(1, 2)))

    assert set(samples(text, METRIC_CHANNEL_REPORTING).values()) == {0}
    assert len(samples(text, METRIC_CHANNEL_REPORTING)) == 2


# ── Ordinary publishing ─────────────────────────────────────────────────────


def test_both_probes_publish_their_own_labelled_gauges():
    text = render(snapshot())

    moisture = samples(text, METRIC_MOISTURE)
    assert moisture['{channel="1",plant="Fiddle Leaf Fig"}'] == 11
    assert moisture['{channel="2",plant="Monstera"}'] == 11


def test_help_is_declared_once_even_though_two_channels_share_a_metric():
    """A duplicate HELP line makes node_exporter reject the whole file."""
    text = render(snapshot())

    assert text.count(f"# HELP {METRIC_MOISTURE} ") == 1
    assert text.count(f"# TYPE {METRIC_MOISTURE} ") == 1


def test_the_gateway_ambient_sensor_is_published_without_channel_labels():
    text = render(snapshot())

    assert "ecowitt_ambient_temperature_fahrenheit 71.4" in text
    assert "ecowitt_ambient_humidity_percent 59" in text


def test_a_failed_run_publishes_no_channel_metrics_at_all():
    """No payload means the gateway was unreachable -- a different failure.

    Emitting reporting=0 here would blame the probes for a network problem and
    send Greg to the batteries instead of to the VLAN.
    """
    text = PUBLISHER.render(
        RunMetrics(exit_code=2, duration_seconds=30.0, payload=None), now=1000.0
    )

    assert METRIC_CHANNEL_REPORTING not in text
    assert "ecowitt_sensor_read_ok 0" in text


def test_the_publisher_writes_its_own_file_not_the_aranet_one():
    """Both collectors share officepi's textfile directory."""
    assert METRICS_FILENAME == "ecowitt.prom"
    assert PUBLISHER.filename == "ecowitt.prom"


def test_every_metric_is_namespaced_to_this_collector():
    text = render(snapshot())

    for line in text.splitlines():
        if line and not line.startswith("#"):
            assert line.startswith("ecowitt_"), f"{line!r} escaped the namespace"


# ── InfluxDB points ─────────────────────────────────────────────────────────


def test_one_point_is_written_per_reporting_channel_plus_ambient():
    points = build_points(
        snapshot(), device_name="ecowitt-gw1200b", location="living room", timestamp=1
    )

    lines = [point.to_line_protocol() for point in points]
    assert len([line for line in lines if line.startswith(MEASUREMENT_SOIL)]) == 2
    assert len([line for line in lines if line.startswith(MEASUREMENT_AMBIENT)]) == 1


def test_a_point_carries_the_channel_and_plant_as_tags():
    points = build_points(
        snapshot(), device_name="ecowitt-gw1200b", location="living room", timestamp=1
    )

    line = next(
        line
        for line in (point.to_line_protocol() for point in points)
        if "channel=1" in line
    )

    assert "plant=Fiddle\\ Leaf\\ Fig" in line
    assert "location=living\\ room" in line


def test_integer_fields_stay_integers_so_influx_never_rejects_a_later_write():
    """InfluxDB pins a field's type on first write. A 34 that becomes 34.0 fails."""
    points = build_points(
        snapshot(), device_name="d", location="l", timestamp=1
    )

    line = next(
        line
        for line in (point.to_line_protocol() for point in points)
        if "channel=1" in line
    )

    assert "moisture=11i" in line
    assert "battery_level=5i" in line
    assert "ec=0" in line


def test_every_point_in_a_snapshot_shares_one_timestamp():
    """Otherwise 'were these pots read at the same moment?' is unanswerable."""
    points = build_points(
        snapshot(), device_name="d", location="l", timestamp=1785772800
    )

    stamps = {point.to_line_protocol().rsplit(" ", 1)[-1] for point in points}
    assert len(stamps) == 1


def test_a_snapshot_with_no_reporting_probes_produces_no_points():
    points = build_points(
        snapshot(payload={"ch_ec": []}, expected=(1, 2)),
        device_name="d",
        location="l",
        timestamp=1,
    )

    assert points == []
