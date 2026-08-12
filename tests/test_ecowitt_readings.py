"""Tests for parsing the Ecowitt GW1200B's /get_livedata_info payload.

Everything the gateway returns is a STRING with the unit baked into it
("11%", "0 uS/cm"), and the temperature unit follows a gateway-wide display
setting. That makes parsing the part most likely to go quietly wrong, so the
real payload is pinned as a fixture and the unit handling is tested in both
directions.

The single most important behaviour here is the LAST test: a sensor that has
stopped reporting must never be indistinguishable from a healthy one. That is
the failure that matters while the house is empty.
"""

import json
import pathlib

import pytest

from ecowitt.readings import (
    MAX_BATTERY_LEVEL,
    ChannelReading,
    GatewaySnapshot,
    ReadingError,
    parse_livedata,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "livedata_two_soil_channels.json"

EXPECTED_CHANNELS = (1, 2)


def real_payload():
    return json.loads(FIXTURE.read_text())


def payload_with_channels(*channels):
    """A minimal payload carrying exactly the given ch_ec entries."""
    return {"wh25": [], "ch_ec": list(channels), "common_list": []}


def channel(number, **overrides):
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


# ── Parsing the real device output ──────────────────────────────────────────


def test_parses_the_real_gateway_payload_into_both_channels():
    """Ground truth captured from the GW1200B at 10.20.10.156."""
    snapshot = parse_livedata(real_payload(), expected_channels=EXPECTED_CHANNELS)

    assert sorted(reading.channel for reading in snapshot.channels) == [1, 2]
    assert snapshot.reading_for(1).moisture_percent == 11
    assert snapshot.reading_for(2).moisture_percent == 11
    assert snapshot.reading_for(1).ec_microsiemens_per_cm == 0.0


def test_strips_units_from_the_percent_and_ec_strings():
    snapshot = parse_livedata(
        payload_with_channels(channel(1, humidity="47%", ec="1350 uS/cm")),
        expected_channels=(1,),
    )
    reading = snapshot.reading_for(1)

    assert reading.moisture_percent == 47
    assert reading.ec_microsiemens_per_cm == 1350.0


def test_reads_battery_as_a_level_out_of_five_not_a_percentage():
    """A WH51 reports 0-5 battery LEVELS. Treating 5 as "5%" would page nightly."""
    reading = parse_livedata(
        payload_with_channels(channel(1, battery="5", voltage="1.56")),
        expected_channels=(1,),
    ).reading_for(1)

    assert reading.battery_level == 5
    assert MAX_BATTERY_LEVEL == 5
    assert reading.battery_volts == pytest.approx(1.56)


# ── The temperature unit trap ───────────────────────────────────────────────


def test_fahrenheit_payload_is_stored_canonically_as_celsius():
    reading = parse_livedata(
        payload_with_channels(channel(1, temp="69.8", unit="F")), expected_channels=(1,)
    ).reading_for(1)

    assert reading.temperature_c == pytest.approx(21.0)
    assert reading.temperature_f == pytest.approx(69.8)


def test_celsius_payload_is_honoured_rather_than_assumed_to_be_fahrenheit():
    """The unit follows a gateway display setting Greg can flip in the web UI.

    Assuming Fahrenheit would silently turn 21 C into -6.1 C and quietly poison
    a year of history without ever failing a run.
    """
    reading = parse_livedata(
        payload_with_channels(channel(1, temp="21.0", unit="C")), expected_channels=(1,)
    ).reading_for(1)

    assert reading.temperature_c == pytest.approx(21.0)
    assert reading.temperature_f == pytest.approx(69.8)


def test_an_unrecognised_temperature_unit_fails_loudly_instead_of_guessing():
    with pytest.raises(ReadingError, match="unit"):
        parse_livedata(
            payload_with_channels(channel(1, temp="21.0", unit="K")),
            expected_channels=(1,),
        )


# ── Plausibility ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_moisture", ["101%", "-1%"])
def test_impossible_moisture_is_rejected(bad_moisture):
    with pytest.raises(ReadingError, match="moisture"):
        parse_livedata(
            payload_with_channels(channel(1, humidity=bad_moisture)),
            expected_channels=(1,),
        )


def test_negative_ec_is_rejected():
    with pytest.raises(ReadingError, match="[Ee]C"):
        parse_livedata(
            payload_with_channels(channel(1, ec="-5 uS/cm")), expected_channels=(1,)
        )


def test_a_non_numeric_field_is_rejected_rather_than_silently_zeroed():
    """A partial gateway response must fail the read, not write 0 into history."""
    with pytest.raises(ReadingError):
        parse_livedata(
            payload_with_channels(channel(1, humidity="--%")), expected_channels=(1,)
        )


# ── Ambient conditions from the gateway's own sensor ────────────────────────


def test_the_gateway_ambient_sensor_is_captured_when_present():
    """Room temperature and humidity are what actually drive the drying rate."""
    snapshot = parse_livedata(real_payload(), expected_channels=EXPECTED_CHANNELS)

    assert snapshot.ambient is not None
    assert snapshot.ambient.temperature_f == pytest.approx(71.4)
    assert snapshot.ambient.humidity_percent == 59


def test_a_payload_with_no_ambient_block_still_parses():
    snapshot = parse_livedata(
        payload_with_channels(channel(1)), expected_channels=(1,)
    )

    assert snapshot.ambient is None
    assert snapshot.reading_for(1) is not None


# ── The failure that matters most while nobody is home ──────────────────────


def test_a_channel_that_stops_reporting_is_recorded_as_missing_not_omitted():
    """A dead probe must never look like a healthy one.

    If channel 2's battery dies the gateway simply stops listing it. Silently
    parsing "the channels that happen to be present" would mean a dead sensor
    and a thriving plant produce the same, alert-free output -- which is the
    exact way this system would fail Tracy's plants while the house is empty.
    """
    snapshot = parse_livedata(
        payload_with_channels(channel(1)), expected_channels=(1, 2)
    )

    assert snapshot.is_reporting(1) is True
    assert snapshot.is_reporting(2) is False
    assert snapshot.missing_channels == (2,)
    assert snapshot.reading_for(2) is None


def test_every_expected_channel_missing_is_a_valid_snapshot_not_a_read_failure():
    """Reaching the gateway and finding no sensors EXONERATES the network.

    Raising here would surface as "sensor read failed", which is the same signal
    as the gateway being unreachable and would send Greg to the wrong end of the
    house. The per-channel reporting metric carries this instead.
    """
    snapshot = parse_livedata(payload_with_channels(), expected_channels=(1, 2))

    assert snapshot.missing_channels == (1, 2)
    assert snapshot.channels == ()


def test_an_unexpected_extra_channel_is_still_captured():
    """Greg pairing a third probe must show up in data before anyone edits config."""
    snapshot = parse_livedata(
        payload_with_channels(channel(1), channel(3)), expected_channels=(1,)
    )

    assert snapshot.is_reporting(3) is True
    assert snapshot.reading_for(3).channel == 3


def test_snapshot_exposes_channels_in_a_stable_order():
    snapshot = parse_livedata(
        payload_with_channels(channel(3), channel(1), channel(2)),
        expected_channels=(1, 2, 3),
    )

    assert [reading.channel for reading in snapshot.channels] == [1, 2, 3]


# ── Naming ──────────────────────────────────────────────────────────────────


def test_a_channel_uses_its_configured_plant_name_over_the_gateways_blank_one():
    snapshot = parse_livedata(
        payload_with_channels(channel(1, name="")),
        expected_channels=(1,),
        channel_names={1: "Fiddle Leaf Fig"},
    )

    assert snapshot.reading_for(1).plant == "Fiddle Leaf Fig"


def test_an_unnamed_channel_falls_back_to_a_stable_label():
    reading = parse_livedata(
        payload_with_channels(channel(1, name="")), expected_channels=(1,)
    ).reading_for(1)

    assert reading.plant == "channel 1"
