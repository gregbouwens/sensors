"""Tests for the shared node_exporter textfile publisher.

The per-collector invariants (carry-forward, no-watermark-on-first-failure) are
pinned through the Aranet4 in tests/test_metrics.py. What is tested HERE is the
machinery the multi-channel Ecowitt collector added: labelled samples, and the
exposition-format rules that a second collector can newly violate.

node_exporter parses the whole textfile directory on every scrape. A malformed
line in one file is not a local problem -- it costs the scrape, taking the
Aranet4's metrics down alongside the soil probes'.
"""

import pytest

from sensorcore.textfile import (
    SUFFIX_RUN_EXIT_CODE,
    RunMetrics,
    Sample,
    TextfilePublisher,
    format_labels,
)


def publisher(payload_samples=lambda payload: []):
    return TextfilePublisher(
        prefix="probe", filename="probe.prom", payload_samples=payload_samples
    )


def sample_lines(text):
    return [line for line in text.splitlines() if line and not line.startswith("#")]


def test_every_metric_name_is_prefixed_with_the_collectors_namespace():
    """Two collectors share one textfile directory; namespaces must not collide."""
    text = publisher().render(
        RunMetrics(exit_code=0, duration_seconds=1.0, payload=None), now=1000.0
    )

    for line in sample_lines(text):
        assert line.startswith("probe_"), f"{line!r} escaped the collector's namespace"


def test_labelled_samples_render_in_exposition_format():
    text = publisher(
        lambda payload: [
            Sample("soil_moisture_percent", 34, "Soil moisture.", {"channel": "1"}),
            Sample("soil_moisture_percent", 51, "Soil moisture.", {"channel": "2"}),
        ]
    ).render(RunMetrics(exit_code=0, duration_seconds=1.0, payload=object()), now=1000.0)

    assert 'probe_soil_moisture_percent{channel="1"} 34' in text
    assert 'probe_soil_moisture_percent{channel="2"} 51' in text


def test_help_and_type_are_declared_once_per_metric_name_not_once_per_sample():
    """A repeated HELP line makes node_exporter reject the ENTIRE file.

    This is the failure mode a per-channel metric introduces and a single-valued
    collector never could: the same metric name legitimately appears N times.
    """
    text = publisher(
        lambda payload: [
            Sample("soil_moisture_percent", 34, "Soil moisture.", {"channel": "1"}),
            Sample("soil_moisture_percent", 51, "Soil moisture.", {"channel": "2"}),
            Sample("soil_moisture_percent", 12, "Soil moisture.", {"channel": "3"}),
        ]
    ).render(RunMetrics(exit_code=0, duration_seconds=1.0, payload=object()), now=1000.0)

    assert text.count("# HELP probe_soil_moisture_percent ") == 1
    assert text.count("# TYPE probe_soil_moisture_percent ") == 1
    assert len([ln for ln in sample_lines(text) if ln.startswith("probe_soil_moisture")]) == 3


def test_every_emitted_metric_has_a_help_and_type_line():
    text = publisher(
        lambda payload: [Sample("ec_microsiemens", 0, "EC.", {"channel": "1"})]
    ).render(RunMetrics(exit_code=0, duration_seconds=1.0, payload=object()), now=1000.0)

    for line in sample_lines(text):
        name = line.split("{")[0].split(" ")[0]
        assert f"# HELP {name} " in text, f"{name} is missing a HELP line"
        assert f"# TYPE {name} " in text, f"{name} is missing a TYPE line"


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Only backslash, double quote and newline are escaped -- an apostrophe
        # is an ordinary character in the exposition format and must be left
        # alone, or the label value no longer matches what was configured.
        ('Tracy\'s "big" fern', 'plant="Tracy\'s \\"big\\" fern"'),
        ("back\\slash", 'plant="back\\\\slash"'),
        ("two\nlines", 'plant="two\\nlines"'),
    ],
)
def test_label_values_are_escaped(raw, expected):
    """An unescaped quote in a plant nickname corrupts the whole scrape.

    Plant names are user-supplied, so this is reachable by typing a name into
    the config -- not a theoretical edge case.
    """
    assert format_labels({"plant": raw}) == "{" + expected + "}"


def test_labels_render_in_a_stable_order():
    """Unordered dict iteration would churn the file and the scrape diff."""
    labels = {"plant": "fern", "channel": "1", "location": "kitchen"}

    assert format_labels(labels) == '{channel="1",location="kitchen",plant="fern"}'


def test_no_labels_renders_a_bare_metric_name():
    text = publisher().render(
        RunMetrics(exit_code=0, duration_seconds=1.0, payload=None), now=1000.0
    )

    assert f"probe_{SUFFIX_RUN_EXIT_CODE} 0" in text


def test_a_collector_may_sharpen_the_generic_run_metric_help_text():
    sharpened = TextfilePublisher(
        prefix="probe",
        filename="probe.prom",
        payload_samples=lambda payload: [],
        run_help={"sensor_read_ok": "1 if the last run reached the gateway over HTTP."},
    )

    text = sharpened.render(
        RunMetrics(exit_code=0, duration_seconds=1.0, payload=None), now=1000.0
    )

    assert "# HELP probe_sensor_read_ok 1 if the last run reached the gateway over HTTP." in text
