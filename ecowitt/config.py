"""Environment-driven configuration for the Ecowitt soil collector.

Settings are prefixed ECOWITT_ where they are this collector's own, and shared
unprefixed with the Aranet4 job where they describe the same thing -- one
InfluxDB, one textfile directory. Both jobs read the same .env on officepi, so
an unprefixed ECOWITT setting would silently reconfigure the Aranet4.

ECOWITT_CHANNELS is the only unusual one. It declares which probes are expected
AND what to call them in a single value::

    ECOWITT_CHANNELS=1:Fiddle Leaf Fig,2:Monstera
    ECOWITT_CHANNELS=1,2                     # names optional

One setting rather than two, because the "expected" list is what makes a dead
probe visible. Split across two settings they would drift, and a channel
quietly dropping out of the expected list is precisely how a flat battery stops
being alerted on.
"""

from dataclasses import dataclass, field

from sensorcore import config as core

ENV_INFLUX_BUCKET = "ECOWITT_INFLUX_BUCKET"
ENV_GATEWAY_URL = "ECOWITT_GATEWAY_URL"
ENV_CHANNELS = "ECOWITT_CHANNELS"
ENV_LOCATION = "ECOWITT_LOCATION"
ENV_DEVICE_NAME = "ECOWITT_DEVICE_NAME"
ENV_LOG_PATH = "ECOWITT_LOG_PATH"
ENV_TIMEOUT_SECONDS = "ECOWITT_TIMEOUT_SECONDS"

REQUIRED_SETTINGS = core.INFLUX_CONNECTION_SETTINGS + (
    ENV_INFLUX_BUCKET,
    ENV_GATEWAY_URL,
    ENV_CHANNELS,
    ENV_LOCATION,
)

DEFAULT_DEVICE_NAME = "ecowitt-gw1200b"
DEFAULT_LOG_FILENAME = "ecowitt_logger.log"

# The gateway is on the far side of a VLAN boundary and answers in ~70ms. Ten
# seconds is generous; the point of a bound is that a hung socket must not leave
# a cron job running into the next one.
DEFAULT_TIMEOUT_SECONDS = 10.0

LIVEDATA_PATH = "/get_livedata_info"

# A GW1200B addresses soil channels 1-8. Anything outside that would be accepted
# happily, never report, and look exactly like a dead sensor forever.
MIN_CHANNEL = 1
MAX_CHANNEL = 8

CHANNEL_SEPARATOR = ","
NAME_SEPARATOR = ":"


def _parse_channels(raw):
    """Parse 'ECOWITT_CHANNELS' into (ordered channels, {channel: name})."""
    channels = []
    names = {}

    for item in raw.split(CHANNEL_SEPARATOR):
        entry = item.strip()
        if not entry:
            continue

        number, _, name = entry.partition(NAME_SEPARATOR)
        try:
            channel = int(number.strip())
        except ValueError as error:
            raise core.ConfigError(
                f"{ENV_CHANNELS}: {number.strip()!r} is not a channel number "
                f"(expected {MIN_CHANNEL}-{MAX_CHANNEL}, as in '1:Fern,2:Monstera')"
            ) from error

        if not MIN_CHANNEL <= channel <= MAX_CHANNEL:
            raise core.ConfigError(
                f"{ENV_CHANNELS}: channel {channel} is outside the gateway's "
                f"range {MIN_CHANNEL}-{MAX_CHANNEL}"
            )

        if channel not in channels:
            channels.append(channel)
        if name.strip():
            names[channel] = name.strip()

    if not channels:
        raise core.ConfigError(
            f"{ENV_CHANNELS} lists no channels -- a collector that expects "
            "nothing would report perfect health forever"
        )

    return tuple(sorted(channels)), names


def _normalise_url(raw):
    """Accept 'ecowitt.dbmob.nl' as well as a full URL, and drop trailing slashes.

    DNS names over IPs is the homelab convention, so requiring a scheme would
    just be a footgun on the value most likely to be typed by hand.
    """
    url = raw.strip().rstrip("/")
    if "://" not in url:
        url = f"http://{url}"
    return url


@dataclass(frozen=True)
class Config:
    influx_url: str
    influx_token: str = field(repr=False)  # never let a traceback leak the token
    influx_org: str
    influx_bucket: str
    gateway_url: str
    expected_channels: tuple
    channel_names: dict
    location: str
    device_name: str
    textfile_dir: str
    log_path: str
    timezone: str
    max_retries: int
    retry_delay_seconds: float
    timeout_seconds: float

    @property
    def livedata_url(self):
        return f"{self.gateway_url}{LIVEDATA_PATH}"

    @classmethod
    def from_env(cls, env=None):
        import os

        env = os.environ if env is None else env
        values = core.require_all(env, REQUIRED_SETTINGS)
        channels, names = _parse_channels(values[ENV_CHANNELS])

        return cls(
            influx_url=values[core.ENV_INFLUX_URL],
            influx_token=values[core.ENV_INFLUX_TOKEN],
            influx_org=values[core.ENV_INFLUX_ORG],
            influx_bucket=values[ENV_INFLUX_BUCKET],
            gateway_url=_normalise_url(values[ENV_GATEWAY_URL]),
            expected_channels=channels,
            channel_names=names,
            location=values[ENV_LOCATION],
            device_name=core.optional(env, ENV_DEVICE_NAME, DEFAULT_DEVICE_NAME),
            textfile_dir=core.textfile_dir(env),
            log_path=core.optional(
                env,
                ENV_LOG_PATH,
                f"{core.repo_root()}/{DEFAULT_LOG_FILENAME}",
            ),
            timezone=core.timezone(env),
            max_retries=core.max_retries(env),
            retry_delay_seconds=core.retry_delay_seconds(env),
            timeout_seconds=core.number(
                env, ENV_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS, float
            ),
        )
