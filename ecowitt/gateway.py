"""The Ecowitt GW1200B's local HTTP API.

Thin adapter: fetch /get_livedata_info, hand the JSON to the parser, return a
validated snapshot. Everything above this line is testable without a gateway.

Uses stdlib urllib rather than `requests` on purpose -- this is one unauthenticated
GET returning a few hundred bytes, and officepi is a Raspberry Pi whose venv is
one more thing to keep in sync at deploy time.

**Why polling, not pushing.** The gateway can push readings to a custom endpoint
on a schedule, which would avoid this request entirely. It cannot be used here:
the gateway lives on the Arlo (untrusted IoT) VLAN, and while the homelab can
reach Arlo, Arlo cannot reach the homelab. A push would have to cross the
blocked direction. Polling is not a workaround for that rule, it is the shape
the rule dictates -- and it keeps the untrusted device unable to initiate
anything.
"""

import json
import socket
import urllib.error
import urllib.request

from .readings import ReadingError, parse_livedata

# Everything that can go wrong between here and the gateway is transient on a
# 5-minute cron: a Wi-Fi blip on the IoT VLAN, the gateway rebooting after a
# firmware update, a half-sent response. ReadingError is included because a
# truncated payload is a transport failure wearing a parser's clothes. Nothing
# is swallowed -- an exhausted retry still fails the run and is reported through
# the metrics file.
GATEWAY_RETRYABLE_ERRORS = (
    urllib.error.URLError,
    urllib.error.HTTPError,
    socket.timeout,
    OSError,
    json.JSONDecodeError,
    ReadingError,
)

USER_AGENT = "homelab-sensors/ecowitt (+officepi)"


def fetch_json(url, timeout_seconds):
    """GET a URL and decode the JSON body.

    The gateway answers `Content-Type: text/html` for its JSON endpoints, so the
    content type is deliberately not checked -- trusting it would reject every
    valid response this device has ever sent.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


class EcowittGateway:
    """Reads every paired soil probe from one gateway."""

    retryable_errors = GATEWAY_RETRYABLE_ERRORS
    description = "read the Ecowitt gateway"

    def __init__(self, config, fetch=fetch_json):
        self._config = config
        self._fetch = fetch

    def read(self):
        """Return a validated GatewaySnapshot, or raise."""
        payload = self._fetch(self._config.livedata_url, self._config.timeout_seconds)
        return parse_livedata(
            payload,
            expected_channels=self._config.expected_channels,
            channel_names=self._config.channel_names,
        )
