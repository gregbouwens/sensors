"""Environment-driven configuration.

Every setting is named by a constant -- no magic strings scattered through the
job -- and a missing or blank value is reported explicitly, all at once, so a
broken .env costs one fix instead of five cron cycles.
"""

import os
from dataclasses import dataclass, field

ENV_INFLUX_URL = "INFLUX_URL"
ENV_INFLUX_TOKEN = "INFLUXDB_TOKEN"
ENV_INFLUX_ORG = "INFLUX_ORG"
ENV_INFLUX_BUCKET = "INFLUX_BUCKET"
ENV_ARANET_MAC = "ARANET_MAC"
ENV_DEVICE_NAME = "DEVICE_NAME"
ENV_LOCATION = "LOCATION"

ENV_TEXTFILE_DIR = "TEXTFILE_COLLECTOR_DIR"
ENV_LOG_PATH = "LOG_PATH"
ENV_TIMEZONE = "LOG_TIMEZONE"
ENV_MAX_RETRIES = "MAX_RETRIES"
ENV_RETRY_DELAY_SECONDS = "RETRY_DELAY_SECONDS"

REQUIRED_SETTINGS = (
    ENV_INFLUX_URL,
    ENV_INFLUX_TOKEN,
    ENV_INFLUX_ORG,
    ENV_INFLUX_BUCKET,
    ENV_ARANET_MAC,
    ENV_DEVICE_NAME,
    ENV_LOCATION,
)

# node_exporter's textfile collector directory on officepi. Overridable so the
# job runs on a dev box with no node_exporter installed.
DEFAULT_TEXTFILE_DIR = "/var/lib/node_exporter/textfile_collector"
DEFAULT_LOG_FILENAME = "aranet_logger.log"
DEFAULT_TIMEZONE = "America/Los_Angeles"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 5.0

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ConfigError(Exception):
    """Configuration is missing or unusable. Not retryable."""


def _require(env, missing):
    def read(name):
        value = env.get(name, "")
        if not value.strip():
            missing.append(name)
            return ""
        return value.strip()

    return read


def _number(env, name, default, parse):
    raw = env.get(name, "")
    if not raw.strip():
        return default
    try:
        return parse(raw.strip())
    except ValueError as error:
        raise ConfigError(f"{name} must be numeric, got {raw!r}") from error


@dataclass(frozen=True)
class Config:
    influx_url: str
    influx_token: str = field(repr=False)  # never let a traceback leak the token
    influx_org: str
    influx_bucket: str
    aranet_mac: str
    device_name: str
    location: str
    textfile_dir: str
    log_path: str
    timezone: str
    max_retries: int
    retry_delay_seconds: float

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        missing = []
        read = _require(env, missing)

        values = {name: read(name) for name in REQUIRED_SETTINGS}

        if missing:
            raise ConfigError(
                "Missing or blank required settings: " + ", ".join(sorted(missing))
            )

        return cls(
            influx_url=values[ENV_INFLUX_URL],
            influx_token=values[ENV_INFLUX_TOKEN],
            influx_org=values[ENV_INFLUX_ORG],
            influx_bucket=values[ENV_INFLUX_BUCKET],
            aranet_mac=values[ENV_ARANET_MAC],
            device_name=values[ENV_DEVICE_NAME],
            location=values[ENV_LOCATION],
            textfile_dir=env.get(ENV_TEXTFILE_DIR, "").strip() or DEFAULT_TEXTFILE_DIR,
            log_path=env.get(ENV_LOG_PATH, "").strip()
            or os.path.join(REPO_ROOT, DEFAULT_LOG_FILENAME),
            timezone=env.get(ENV_TIMEZONE, "").strip() or DEFAULT_TIMEZONE,
            max_retries=_number(env, ENV_MAX_RETRIES, DEFAULT_MAX_RETRIES, int),
            retry_delay_seconds=_number(
                env, ENV_RETRY_DELAY_SECONDS, DEFAULT_RETRY_DELAY_SECONDS, float
            ),
        )
