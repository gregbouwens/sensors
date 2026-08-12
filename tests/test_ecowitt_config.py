"""Tests for the Ecowitt collector's configuration.

The interesting part is ECOWITT_CHANNELS. It is the single place that declares
which probes are expected AND what to call them, deliberately: two separate
settings would drift, and a channel silently dropping out of the "expected" list
is exactly how a dead sensor stops being alerted on.
"""

import pytest

from ecowitt.config import Config
from sensorcore.config import ConfigError

BASE_ENV = {
    "INFLUX_URL": "http://docker20.dbmob.nl:8086",
    "INFLUXDB_TOKEN": "a-token",
    "INFLUX_ORG": "homelab",
    "INFLUX_BUCKET": "homelab",
    "ECOWITT_GATEWAY_URL": "http://10.20.10.156",
    "ECOWITT_CHANNELS": "1:Fiddle Leaf Fig,2:Monstera",
    "ECOWITT_LOCATION": "living room",
    "ECOWITT_INFLUX_BUCKET": "sensors",
}


def env(**overrides):
    merged = {**BASE_ENV, **overrides}
    return {key: value for key, value in merged.items() if value is not None}


def test_a_complete_environment_produces_a_usable_config():
    config = Config.from_env(env())

    assert config.gateway_url == "http://10.20.10.156"
    assert config.expected_channels == (1, 2)
    assert config.channel_names == {1: "Fiddle Leaf Fig", 2: "Monstera"}
    assert config.location == "living room"


def test_every_missing_setting_is_reported_at_once():
    """One fix, not one cron cycle per mistake."""
    with pytest.raises(ConfigError) as raised:
        Config.from_env(env(ECOWITT_GATEWAY_URL=None, INFLUXDB_TOKEN=None))

    message = str(raised.value)
    assert "ECOWITT_GATEWAY_URL" in message
    assert "INFLUXDB_TOKEN" in message


def test_channels_may_be_declared_without_names():
    config = Config.from_env(env(ECOWITT_CHANNELS="1,2,3"))

    assert config.expected_channels == (1, 2, 3)
    assert config.channel_names == {}


def test_channel_names_are_optional_per_channel():
    config = Config.from_env(env(ECOWITT_CHANNELS="1:Fern,2"))

    assert config.expected_channels == (1, 2)
    assert config.channel_names == {1: "Fern"}


def test_whitespace_around_channel_entries_is_tolerated():
    config = Config.from_env(env(ECOWITT_CHANNELS=" 1 : Fiddle Leaf Fig , 2 : Monstera "))

    assert config.expected_channels == (1, 2)
    assert config.channel_names[1] == "Fiddle Leaf Fig"


def test_channels_are_ordered_and_deduplicated():
    config = Config.from_env(env(ECOWITT_CHANNELS="2:Monstera,1:Fern,2:Monstera"))

    assert config.expected_channels == (1, 2)


def test_a_non_numeric_channel_is_rejected_with_a_message_naming_it():
    with pytest.raises(ConfigError, match="ECOWITT_CHANNELS"):
        Config.from_env(env(ECOWITT_CHANNELS="1,kitchen"))


def test_a_channel_outside_the_gateways_range_is_rejected():
    """The GW1200B addresses soil channels 1-8. 9 would never report, silently."""
    with pytest.raises(ConfigError, match="ECOWITT_CHANNELS"):
        Config.from_env(env(ECOWITT_CHANNELS="1,9"))


def test_an_empty_channel_list_is_rejected():
    """A collector expecting nothing would report perfect health forever."""
    with pytest.raises(ConfigError):
        Config.from_env(env(ECOWITT_CHANNELS=","))


def test_the_influx_token_is_kept_out_of_the_repr():
    """A traceback in cron.log must not become a credential leak."""
    config = Config.from_env(env())

    assert "a-token" not in repr(config)


def test_defaults_are_applied_for_optional_settings():
    config = Config.from_env(env())

    assert config.max_retries == 3
    assert config.retry_delay_seconds == 5.0
    assert config.timezone == "America/Los_Angeles"
    assert config.timeout_seconds > 0


def test_a_bare_host_is_accepted_and_normalised_to_a_url():
    """DNS names are the homelab convention; a scheme should not be mandatory."""
    config = Config.from_env(env(ECOWITT_GATEWAY_URL="ecowitt.dbmob.nl"))

    assert config.gateway_url == "http://ecowitt.dbmob.nl"


def test_a_trailing_slash_on_the_gateway_url_does_not_double_up():
    config = Config.from_env(env(ECOWITT_GATEWAY_URL="http://10.20.10.156/"))

    assert config.livedata_url == "http://10.20.10.156/get_livedata_info"


def test_the_bucket_is_this_collectors_own_not_the_shared_influx_bucket():
    """Soil readings must never land in the Aranet4's bucket.

    INFLUX_URL/TOKEN/ORG describe one server and are shared, but both jobs read
    the same .env on officepi -- so inheriting INFLUX_BUCKET would have written
    soil moisture into `aranet4` alongside a year of CO2 history.
    """
    config = Config.from_env(env(INFLUX_BUCKET="aranet4"))

    assert config.influx_bucket == "sensors"


def test_a_missing_ecowitt_bucket_is_not_silently_inherited():
    with pytest.raises(ConfigError, match="ECOWITT_INFLUX_BUCKET"):
        Config.from_env(env(ECOWITT_INFLUX_BUCKET=None, INFLUX_BUCKET="aranet4"))
