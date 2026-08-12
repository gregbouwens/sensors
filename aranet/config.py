"""Environment-driven configuration for the Aranet4 job.

Every setting is named by a constant -- no magic strings scattered through the
job -- and a missing or blank value is reported explicitly, all at once, so a
broken .env costs one fix instead of five cron cycles. That validation, and the
settings shared with every other collector on the host, live in
sensorcore.config; what remains here is the Aranet4's own.
"""

from dataclasses import dataclass, field

from sensorcore import config as core
from sensorcore.config import (  # re-exported: the aranet-facing spelling
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    DEFAULT_TEXTFILE_DIR,
    DEFAULT_TIMEZONE,
    ENV_INFLUX_BUCKET,
    ENV_INFLUX_ORG,
    ENV_INFLUX_TOKEN,
    ENV_INFLUX_URL,
    ENV_MAX_RETRIES,
    ENV_RETRY_DELAY_SECONDS,
    ENV_TEXTFILE_DIR,
    ENV_TIMEZONE,
    ConfigError,
)

ENV_ARANET_MAC = "ARANET_MAC"
ENV_DEVICE_NAME = "DEVICE_NAME"
ENV_LOCATION = "LOCATION"
ENV_LOG_PATH = "LOG_PATH"

REQUIRED_SETTINGS = core.INFLUX_CONNECTION_SETTINGS + (
    ENV_INFLUX_BUCKET,
    ENV_ARANET_MAC,
    ENV_DEVICE_NAME,
    ENV_LOCATION,
)

DEFAULT_LOG_FILENAME = "aranet_logger.log"

REPO_ROOT = core.repo_root()

__all__ = [
    "Config",
    "ConfigError",
    "DEFAULT_LOG_FILENAME",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_DELAY_SECONDS",
    "DEFAULT_TEXTFILE_DIR",
    "DEFAULT_TIMEZONE",
    "ENV_ARANET_MAC",
    "ENV_DEVICE_NAME",
    "ENV_INFLUX_BUCKET",
    "ENV_INFLUX_ORG",
    "ENV_INFLUX_TOKEN",
    "ENV_INFLUX_URL",
    "ENV_LOCATION",
    "ENV_LOG_PATH",
    "ENV_MAX_RETRIES",
    "ENV_RETRY_DELAY_SECONDS",
    "ENV_TEXTFILE_DIR",
    "ENV_TIMEZONE",
    "REQUIRED_SETTINGS",
]


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
        import os

        env = os.environ if env is None else env
        values = core.require_all(env, REQUIRED_SETTINGS)

        return cls(
            influx_url=values[ENV_INFLUX_URL],
            influx_token=values[ENV_INFLUX_TOKEN],
            influx_org=values[ENV_INFLUX_ORG],
            influx_bucket=values[ENV_INFLUX_BUCKET],
            aranet_mac=values[ENV_ARANET_MAC],
            device_name=values[ENV_DEVICE_NAME],
            location=values[ENV_LOCATION],
            textfile_dir=core.textfile_dir(env),
            log_path=core.optional(
                env, ENV_LOG_PATH, os.path.join(REPO_ROOT, DEFAULT_LOG_FILENAME)
            ),
            timezone=core.timezone(env),
            max_retries=core.max_retries(env),
            retry_delay_seconds=core.retry_delay_seconds(env),
        )
