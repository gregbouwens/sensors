"""Tests for the Ecowitt gateway HTTP adapter.

The fetch function is injected, so the whole adapter is exercised without a
gateway, without a network and without the Arlo VLAN.
"""

import json
import pathlib
import socket
import urllib.error

import pytest

from ecowitt.config import Config
from ecowitt.gateway import EcowittGateway
from ecowitt.readings import ReadingError

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "livedata_two_soil_channels.json"

ENV = {
    "INFLUX_URL": "http://docker20.dbmob.nl:8086",
    "INFLUXDB_TOKEN": "a-token",
    "INFLUX_ORG": "homelab",
    "INFLUX_BUCKET": "homelab",
    "ECOWITT_GATEWAY_URL": "http://10.20.10.156",
    "ECOWITT_CHANNELS": "1:Fiddle Leaf Fig,2:Monstera",
    "ECOWITT_LOCATION": "living room",
    "ECOWITT_INFLUX_BUCKET": "sensors",
}


def config(**overrides):
    return Config.from_env({**ENV, **overrides})


def fetcher(payload, record=None):
    def fetch(url, timeout_seconds):
        if record is not None:
            record.append((url, timeout_seconds))
        if isinstance(payload, Exception):
            raise payload
        return payload

    return fetch


def test_a_successful_poll_returns_a_named_snapshot():
    snapshot = EcowittGateway(
        config(), fetch=fetcher(json.loads(FIXTURE.read_text()))
    ).read()

    assert snapshot.reading_for(1).plant == "Fiddle Leaf Fig"
    assert snapshot.reading_for(2).plant == "Monstera"
    assert snapshot.missing_channels == ()


def test_the_configured_channels_and_timeout_reach_the_request():
    calls = []
    EcowittGateway(
        config(ECOWITT_TIMEOUT_SECONDS="4"),
        fetch=fetcher(json.loads(FIXTURE.read_text()), calls),
    ).read()

    assert calls == [("http://10.20.10.156/get_livedata_info", 4.0)]


def test_a_probe_absent_from_the_payload_is_reported_missing():
    snapshot = EcowittGateway(
        config(), fetch=fetcher({"ch_ec": [], "wh25": []})
    ).read()

    assert snapshot.missing_channels == (1, 2)


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("dns went away"),
        socket.timeout("gateway did not answer"),
        OSError("no route to host"),
        json.JSONDecodeError("truncated", "{", 0),
    ],
)
def test_transport_faults_are_declared_retryable(error):
    """A 5-minute cron rides out a Wi-Fi blip or a firmware reboot."""
    assert isinstance(error, EcowittGateway.retryable_errors)


def test_a_truncated_payload_is_retryable_rather_than_fatal():
    """A partial read is a transport failure wearing a parser's clothes."""
    assert issubclass(ReadingError, EcowittGateway.retryable_errors)


def test_a_garbage_payload_raises_rather_than_returning_an_empty_snapshot():
    """Silently returning "no channels" would read as two dead probes."""
    with pytest.raises(ReadingError):
        EcowittGateway(
            config(), fetch=fetcher({"ch_ec": [{"channel": "1", "temp": "boom"}]})
        ).read()


def test_the_adapter_describes_itself_for_the_retry_log():
    assert "Ecowitt" in EcowittGateway.description
