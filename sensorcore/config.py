"""Configuration helpers shared by every collector.

The rule both collectors follow: report EVERY missing setting at once. A broken
.env then costs one fix instead of one cron cycle per mistake -- at five minutes
a cycle, discovering four missing settings one at a time is twenty minutes of
watching a job fail for a reason you already knew about.
"""

import os

ENV_INFLUX_URL = "INFLUX_URL"
ENV_INFLUX_TOKEN = "INFLUXDB_TOKEN"
ENV_INFLUX_ORG = "INFLUX_ORG"
ENV_INFLUX_BUCKET = "INFLUX_BUCKET"

# Settings every collector on the host shares: they describe one InfluxDB
# SERVER, so duplicating them per collector would just be three more things to
# get wrong.
INFLUX_CONNECTION_SETTINGS = (
    ENV_INFLUX_URL,
    ENV_INFLUX_TOKEN,
    ENV_INFLUX_ORG,
)

# The BUCKET is deliberately NOT shared. Collectors write different data with
# different retention needs, and inheriting one bucket name is how the Ecowitt
# job would have quietly written soil readings into the Aranet4's bucket. Each
# collector names its own.

ENV_TEXTFILE_DIR = "TEXTFILE_COLLECTOR_DIR"
ENV_TIMEZONE = "LOG_TIMEZONE"
ENV_MAX_RETRIES = "MAX_RETRIES"
ENV_RETRY_DELAY_SECONDS = "RETRY_DELAY_SECONDS"

# node_exporter's textfile collector directory on officepi. Overridable so a
# collector runs on a dev box with no node_exporter installed.
DEFAULT_TEXTFILE_DIR = "/var/lib/node_exporter/textfile_collector"
DEFAULT_TIMEZONE = "America/Los_Angeles"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 5.0


class ConfigError(Exception):
    """Configuration is missing or unusable. Not retryable."""


def reader(env, missing):
    """Return a read(name) that records blanks instead of raising on the first."""

    def read(name):
        value = env.get(name, "")
        if not value.strip():
            missing.append(name)
            return ""
        return value.strip()

    return read


def require_all(env, names):
    """Read every required setting, raising once with the complete list."""
    missing = []
    read = reader(env, missing)
    values = {name: read(name) for name in names}
    if missing:
        raise ConfigError(
            "Missing or blank required settings: " + ", ".join(sorted(missing))
        )
    return values


def number(env, name, default, parse):
    raw = env.get(name, "")
    if not raw.strip():
        return default
    try:
        return parse(raw.strip())
    except ValueError as error:
        raise ConfigError(f"{name} must be numeric, got {raw!r}") from error


def optional(env, name, default):
    return env.get(name, "").strip() or default


def textfile_dir(env):
    return optional(env, ENV_TEXTFILE_DIR, DEFAULT_TEXTFILE_DIR)


def timezone(env):
    return optional(env, ENV_TIMEZONE, DEFAULT_TIMEZONE)


def max_retries(env):
    return number(env, ENV_MAX_RETRIES, DEFAULT_MAX_RETRIES, int)


def retry_delay_seconds(env):
    return number(env, ENV_RETRY_DELAY_SECONDS, DEFAULT_RETRY_DELAY_SECONDS, float)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
