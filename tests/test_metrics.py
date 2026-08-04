"""Tests for the node_exporter textfile-collector metrics writer.

These metrics are what observethis alerts on, so the invariants here are the
difference between a real page and a false one.
"""

import os

from aranet.metrics import (
    METRIC_LAST_SUCCESS,
    METRIC_RUN_EXIT_CODE,
    METRIC_RUN_TIMESTAMP,
    METRICS_FILENAME,
    RunMetrics,
    read_last_success,
    render,
    write,
)
from aranet.readings import Reading

READING = Reading(
    co2_ppm=612,
    temperature_c=22.2,
    humidity_percent=54,
    pressure_hpa=1012.0,
    battery_percent=91,
)


def parse(text):
    """Parse exposition text into {metric_name: float}, ignoring HELP/TYPE."""
    values = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        name, _, raw = line.partition(" ")
        values[name] = float(raw)
    return values


def test_render_emits_help_and_type_for_every_metric():
    text = render(RunMetrics(exit_code=0, duration_seconds=3.9, reading=READING), now=1000.0)

    emitted = set(parse(text))
    for name in emitted:
        assert f"# HELP {name} " in text, f"{name} is missing a HELP line"
        assert f"# TYPE {name} " in text, f"{name} is missing a TYPE line"


def test_successful_run_records_success_timestamp_and_reading():
    text = render(RunMetrics(exit_code=0, duration_seconds=3.9, reading=READING), now=1000.0)
    values = parse(text)

    assert values[METRIC_RUN_EXIT_CODE] == 0
    assert values[METRIC_RUN_TIMESTAMP] == 1000.0
    assert values[METRIC_LAST_SUCCESS] == 1000.0
    assert values["aranet_sensor_read_ok"] == 1
    assert values["aranet_influx_write_ok"] == 1
    assert values["aranet_run_duration_seconds"] == 3.9
    assert values["aranet_co2_ppm"] == 612
    assert values["aranet_humidity_percent"] == 54
    assert values["aranet_battery_percent"] == 91


def test_failed_run_carries_forward_the_previous_success_timestamp(tmp_path):
    """The invariant that makes the staleness alert meaningful.

    A failing run must not reset the "when did this last work" watermark, or the
    staleness alert would silently re-arm itself on every failure and never fire.
    """
    write(RunMetrics(exit_code=0, duration_seconds=3.9, reading=READING), tmp_path, now=1000.0)
    write(RunMetrics(exit_code=2, duration_seconds=15.0, reading=None), tmp_path, now=1300.0)

    values = parse((tmp_path / METRICS_FILENAME).read_text())

    assert values[METRIC_RUN_TIMESTAMP] == 1300.0, "the run itself did happen"
    assert values[METRIC_LAST_SUCCESS] == 1000.0, "last success must be preserved"
    assert values[METRIC_RUN_EXIT_CODE] == 2
    assert values["aranet_sensor_read_ok"] == 0


def test_failed_run_with_no_prior_success_omits_the_watermark(tmp_path):
    """A fresh deploy must not look like an infinitely stale job.

    Emitting 0 here would make `time() - last_success` enormous and fire the
    staleness alert the moment the collector is enabled. Absent is correct --
    the exit-code alert covers the never-succeeded case instead.
    """
    write(RunMetrics(exit_code=2, duration_seconds=15.0, reading=None), tmp_path, now=1300.0)

    values = parse((tmp_path / METRICS_FILENAME).read_text())

    assert METRIC_LAST_SUCCESS not in values
    assert values[METRIC_RUN_EXIT_CODE] == 2


def test_failed_run_omits_reading_gauges_rather_than_reporting_stale_values(tmp_path):
    write(RunMetrics(exit_code=0, duration_seconds=3.9, reading=READING), tmp_path, now=1000.0)
    write(RunMetrics(exit_code=2, duration_seconds=15.0, reading=None), tmp_path, now=1300.0)

    values = parse((tmp_path / METRICS_FILENAME).read_text())

    assert "aranet_co2_ppm" not in values
    assert "aranet_battery_percent" not in values


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    write(RunMetrics(exit_code=0, duration_seconds=3.9, reading=READING), tmp_path, now=1000.0)

    assert [p.name for p in tmp_path.iterdir()] == [METRICS_FILENAME]


def test_write_is_world_readable_so_node_exporter_can_scrape_it(tmp_path):
    """node_exporter runs as its own unprivileged service account, not as greg."""
    write(RunMetrics(exit_code=0, duration_seconds=3.9, reading=READING), tmp_path, now=1000.0)

    mode = (tmp_path / METRICS_FILENAME).stat().st_mode
    assert mode & 0o044, "node_exporter's service account must be able to read the file"


def test_write_is_a_noop_when_the_textfile_directory_is_absent(tmp_path):
    """Instrumentation must never break the job it instruments."""
    missing = tmp_path / "not-installed"

    write(RunMetrics(exit_code=0, duration_seconds=3.9, reading=READING), missing, now=1000.0)

    assert not missing.exists()


def test_write_replaces_rather_than_appends(tmp_path):
    """A duplicated sample line makes node_exporter reject the whole file."""
    write(RunMetrics(exit_code=0, duration_seconds=3.9, reading=READING), tmp_path, now=1000.0)
    write(RunMetrics(exit_code=0, duration_seconds=4.1, reading=READING), tmp_path, now=1300.0)

    text = (tmp_path / METRICS_FILENAME).read_text()
    sample_lines = [
        line
        for line in text.splitlines()
        if not line.startswith("#") and line.startswith(METRIC_RUN_TIMESTAMP + " ")
    ]

    assert sample_lines == [f"{METRIC_RUN_TIMESTAMP} 1300"]


def test_read_last_success_returns_none_for_a_missing_or_malformed_file(tmp_path):
    assert read_last_success(tmp_path / METRICS_FILENAME) is None

    (tmp_path / METRICS_FILENAME).write_text("garbage not exposition format\n")
    assert read_last_success(tmp_path / METRICS_FILENAME) is None


def test_render_never_emits_scientific_notation(tmp_path):
    """Timestamps are ~1.7e9; %g would render them as 1.7e+09 and lose precision."""
    text = render(RunMetrics(exit_code=0, duration_seconds=3.9, reading=READING), now=1785772800.5)

    assert "e+" not in text.lower()
    assert f"{METRIC_RUN_TIMESTAMP} 1785772800.5" in text
