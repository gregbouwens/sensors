#!/usr/bin/env python3
"""Entrypoint for the 5-minute Aranet4 -> InfluxDB cron job on officepi.

Deliberately thin. Everything worth testing lives in the aranet package; this
file only wires the real sensor and the real database to the run orchestration
and turns the outcome into a process exit code.

    */5 * * * * cd $HOME/repos/sensors && sensors_env/bin/python3 aranet_logger.py

The exit code is a contract with observethis -- see aranet/exit_codes.py.
"""

import os
import sys
import time

from dotenv import load_dotenv

from aranet import metrics
from aranet.config import DEFAULT_TEXTFILE_DIR, ENV_TEXTFILE_DIR, Config, ConfigError
from aranet.exit_codes import EXIT_CONFIG_ERROR
from aranet.job import run
from sensorcore.logging_setup import configure
from aranet.sensor import Aranet4Sensor
from aranet.sink import InfluxSink

RUN_BANNER = "=" * 50


def _report_config_error(error):
    """Publish a config-error metric even though we have no usable Config.

    Without this, a broken .env would leave the metrics file untouched and the
    job would look merely stale rather than misconfigured.
    """
    print(f"Configuration error: {error}", file=sys.stderr)
    metrics.write(
        metrics.RunMetrics(
            exit_code=EXIT_CONFIG_ERROR, duration_seconds=0.0, reading=None
        ),
        os.environ.get(ENV_TEXTFILE_DIR) or DEFAULT_TEXTFILE_DIR,
        now=time.time(),
    )
    return EXIT_CONFIG_ERROR


def main():
    load_dotenv()

    try:
        config = Config.from_env()
    except ConfigError as error:
        return _report_config_error(error)

    logger = configure(config.log_path, config.timezone)
    logger.info(RUN_BANNER)
    logger.info("Starting Aranet4 data collection...")

    outcome = run(
        config,
        Aranet4Sensor(config.aranet_mac),
        InfluxSink(config),
        logger=logger,
    )

    reading = outcome.reading
    if outcome.exit_code == 0 and reading is not None:
        logger.info(
            "Successfully logged: CO2=%dppm, Temp=%.1f°F, Humidity=%d%%, "
            "Pressure=%.1fhPa, Battery=%d%% (took %.2fs)",
            reading.co2_ppm,
            reading.temperature_f,
            reading.humidity_percent,
            reading.pressure_hpa,
            reading.battery_percent,
            outcome.duration_seconds,
        )
    else:
        logger.error(
            "Run failed with exit code %d after %.2fs",
            outcome.exit_code,
            outcome.duration_seconds,
        )

    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
