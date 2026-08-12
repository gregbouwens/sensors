#!/usr/bin/env python3
"""Entrypoint for the 5-minute Ecowitt -> InfluxDB cron job on officepi.

Deliberately thin, like aranet_logger.py. Everything worth testing lives in the
ecowitt and sensorcore packages; this file only wires the real gateway and the
real database to the run orchestration and turns the outcome into an exit code.

    */5 * * * * cd $HOME/repos/sensors && sensors_env/bin/python3 ecowitt_logger.py

The exit code is a contract with observethis -- see sensorcore/exit_codes.py.
"""

import os
import sys
import time

from dotenv import load_dotenv

from ecowitt.config import Config
from ecowitt.gateway import EcowittGateway
from ecowitt.metrics import PUBLISHER
from ecowitt.sink import InfluxSink
from sensorcore.config import (
    DEFAULT_TEXTFILE_DIR,
    ENV_TEXTFILE_DIR,
    ConfigError,
)
from sensorcore.exit_codes import EXIT_CONFIG_ERROR
from sensorcore.job import run
from sensorcore.logging_setup import configure
from sensorcore.textfile import RunMetrics

RUN_BANNER = "=" * 50


def _report_config_error(error):
    """Publish a config-error metric even though we have no usable Config.

    Without this, a broken .env would leave the metrics file untouched and the
    job would look merely stale rather than misconfigured.
    """
    print(f"Configuration error: {error}", file=sys.stderr)
    PUBLISHER.publish(
        RunMetrics(exit_code=EXIT_CONFIG_ERROR, duration_seconds=0.0, payload=None),
        os.environ.get(ENV_TEXTFILE_DIR) or DEFAULT_TEXTFILE_DIR,
        now=time.time(),
    )
    return EXIT_CONFIG_ERROR


def _log_outcome(logger, outcome):
    snapshot = outcome.payload

    if outcome.exit_code != 0 or snapshot is None:
        logger.error(
            "Run failed with exit code %d after %.2fs",
            outcome.exit_code,
            outcome.duration_seconds,
        )
        return

    for reading in snapshot.channels:
        logger.info(
            "ch%d %s: moisture=%d%%, temp=%.1f°F, EC=%.0fuS/cm, battery=%d/5 (%.2fV)",
            reading.channel,
            reading.plant,
            reading.moisture_percent,
            reading.temperature_f,
            reading.ec_microsiemens_per_cm,
            reading.battery_level,
            reading.battery_volts,
        )

    # Logged at WARNING because it is the failure this collector exists to make
    # visible: a probe that has gone silent looks like nothing at all.
    for channel in snapshot.missing_channels:
        logger.warning(
            "ch%d %s did not report -- check the probe's battery or its range "
            "to the gateway",
            channel,
            snapshot.plant_for(channel),
        )

    if snapshot.ambient is not None:
        logger.info(
            "ambient: %.1f°F, %d%% RH",
            snapshot.ambient.temperature_f,
            snapshot.ambient.humidity_percent,
        )

    logger.info(
        "Logged %d of %d expected probes (took %.2fs)",
        len(snapshot.channels),
        len(snapshot.expected_channels),
        outcome.duration_seconds,
    )


def main():
    load_dotenv()

    try:
        config = Config.from_env()
    except ConfigError as error:
        return _report_config_error(error)

    logger = configure(config.log_path, config.timezone)
    logger.info(RUN_BANNER)
    logger.info("Starting Ecowitt soil data collection...")

    outcome = run(
        config,
        EcowittGateway(config),
        InfluxSink(config),
        PUBLISHER,
        logger=logger,
    )

    _log_outcome(logger, outcome)
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
