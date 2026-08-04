"""Aranet4 sensor over Bluetooth LE.

Thin adapter: the only job here is to turn the aranet4 library's reading object
into a validated Reading. Everything above this line is testable without a
Bluetooth adapter.
"""

import aranet4

from .readings import Reading

# BLE reads fail in genuinely diverse ways -- bleak raises BleakError, the stack
# raises OSError when the adapter is wedged, asyncio raises TimeoutError, and a
# partial read surfaces as a ReadingError from validate(). All of them are
# transient on a 5-minute cron, so the sensor path retries broadly. Nothing is
# swallowed: an exhausted retry still fails the run, sets a non-zero exit code
# and is reported through the metrics file.
SENSOR_RETRYABLE_ERRORS = (Exception,)


class Aranet4Sensor:
    retryable_errors = SENSOR_RETRYABLE_ERRORS

    def __init__(self, mac_address):
        self._mac_address = mac_address

    def read(self):
        """Return a validated Reading, or raise."""
        current = aranet4.client.get_current_readings(self._mac_address)
        reading = Reading.from_aranet_current(current)
        reading.validate()
        return reading
