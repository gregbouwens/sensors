"""Tests for the Reading value object and its validation.

Validation thresholds are carried over unchanged from the original logger: they
exist to reject the garbage values an Aranet4 returns when a BLE read is partial.
"""

import pytest

from aranet.readings import Reading, ReadingError, c_to_f


@pytest.mark.parametrize(
    ("celsius", "fahrenheit"),
    [(0.0, 32.0), (100.0, 212.0), (-40.0, -40.0), (22.2, 71.96)],
)
def test_c_to_f(celsius, fahrenheit):
    assert c_to_f(celsius) == pytest.approx(fahrenheit)


def test_temperature_f_is_derived_from_celsius():
    reading = Reading(
        co2_ppm=612, temperature_c=22.2, humidity_percent=54,
        pressure_hpa=1012.0, battery_percent=91,
    )

    assert reading.temperature_f == pytest.approx(71.96)


def test_a_plausible_reading_validates():
    Reading(
        co2_ppm=612, temperature_c=22.2, humidity_percent=54,
        pressure_hpa=1012.0, battery_percent=91,
    ).validate()


@pytest.mark.parametrize(
    ("field", "value", "expected_in_message"),
    [
        ("co2_ppm", 0, "co2"),
        ("co2_ppm", -5, "co2"),
        ("temperature_c", -51.0, "temperature"),
        ("temperature_c", 81.0, "temperature"),
    ],
    ids=["co2-zero", "co2-negative", "temp-too-cold", "temp-too-hot"],
)
def test_implausible_readings_are_rejected_with_a_message_naming_the_field(
    field, value, expected_in_message
):
    kwargs = dict(
        co2_ppm=612, temperature_c=22.2, humidity_percent=54,
        pressure_hpa=1012.0, battery_percent=91,
    )
    kwargs[field] = value

    with pytest.raises(ReadingError) as excinfo:
        Reading(**kwargs).validate()

    assert expected_in_message in str(excinfo.value).lower()


def test_boundary_temperatures_are_accepted():
    """-50 and 80 are the inclusive bounds -- don't reject a legitimate edge."""
    for celsius in (-50.0, 80.0):
        Reading(
            co2_ppm=612, temperature_c=celsius, humidity_percent=54,
            pressure_hpa=1012.0, battery_percent=91,
        ).validate()


def test_from_aranet_current_maps_the_library_object():
    """Thin adapter over the aranet4 library's reading object."""

    class FakeCurrent:
        co2 = 612
        temperature = 22.2
        humidity = 54
        pressure = 1012.0
        battery = 91

    reading = Reading.from_aranet_current(FakeCurrent())

    assert reading.co2_ppm == 612
    assert reading.temperature_c == pytest.approx(22.2)
    assert reading.battery_percent == 91
