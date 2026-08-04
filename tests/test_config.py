"""Tests for environment-driven configuration.

Fail fast and explicitly: a missing variable must name itself, and all missing
variables must be reported at once so a broken .env takes one fix, not five runs.
"""

import pytest

from aranet.config import DEFAULT_TEXTFILE_DIR, Config, ConfigError

COMPLETE_ENV = {
    "INFLUX_URL": "http://docker20.dbmob.nl:8086",
    "INFLUXDB_TOKEN": "a-token",
    "INFLUX_ORG": "homelab",
    "INFLUX_BUCKET": "homelab",
    "ARANET_MAC": "AA:BB:CC:DD:EE:FF",
    "DEVICE_NAME": "aranet4-office",
    "LOCATION": "office",
}


def test_from_env_reads_every_required_setting():
    config = Config.from_env(COMPLETE_ENV)

    assert config.influx_url == "http://docker20.dbmob.nl:8086"
    assert config.influx_token == "a-token"
    assert config.influx_org == "homelab"
    assert config.influx_bucket == "homelab"
    assert config.aranet_mac == "AA:BB:CC:DD:EE:FF"
    assert config.device_name == "aranet4-office"
    assert config.location == "office"


def test_missing_variables_are_all_reported_in_one_error():
    env = {k: v for k, v in COMPLETE_ENV.items() if k not in ("INFLUXDB_TOKEN", "ARANET_MAC")}

    with pytest.raises(ConfigError) as excinfo:
        Config.from_env(env)

    message = str(excinfo.value)
    assert "INFLUXDB_TOKEN" in message
    assert "ARANET_MAC" in message
    assert "INFLUX_URL" not in message, "settings that ARE present must not be reported missing"


def test_blank_values_count_as_missing():
    """An empty .env line is the common real-world failure, not an absent key."""
    env = dict(COMPLETE_ENV, INFLUXDB_TOKEN="   ")

    with pytest.raises(ConfigError, match="INFLUXDB_TOKEN"):
        Config.from_env(env)


def test_textfile_dir_defaults_to_the_node_exporter_collector_path():
    assert Config.from_env(COMPLETE_ENV).textfile_dir == DEFAULT_TEXTFILE_DIR


def test_textfile_dir_is_overridable_for_dev_boxes():
    env = dict(COMPLETE_ENV, TEXTFILE_COLLECTOR_DIR="/tmp/textfile")

    assert Config.from_env(env).textfile_dir == "/tmp/textfile"


def test_retry_settings_have_defaults_and_are_overridable():
    assert Config.from_env(COMPLETE_ENV).max_retries == 3

    env = dict(COMPLETE_ENV, MAX_RETRIES="5", RETRY_DELAY_SECONDS="2")
    config = Config.from_env(env)

    assert config.max_retries == 5
    assert config.retry_delay_seconds == 2.0


def test_a_non_numeric_retry_setting_is_a_config_error_not_a_crash_mid_run():
    env = dict(COMPLETE_ENV, MAX_RETRIES="lots")

    with pytest.raises(ConfigError, match="MAX_RETRIES"):
        Config.from_env(env)


def test_the_token_is_not_exposed_by_repr():
    """A traceback or debug log must never leak the InfluxDB token."""
    config = Config.from_env(COMPLETE_ENV)

    assert "a-token" not in repr(config)
