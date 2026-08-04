"""Logging configured for the local timezone.

Uses stdlib zoneinfo rather than pytz -- one fewer dependency, and it is what
the standard library has shipped since 3.9.
"""

import datetime
import logging
from zoneinfo import ZoneInfo

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"


class LocalTimeFormatter(logging.Formatter):
    """Stamps records in a named timezone instead of the host's UTC offset."""

    def __init__(self, fmt=None, datefmt=None, tz=None):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._tz = tz

    def formatTime(self, record, datefmt=None):
        stamped = datetime.datetime.fromtimestamp(record.created, self._tz)
        return stamped.strftime(datefmt) if datefmt else stamped.isoformat()


def configure(log_path, timezone, level=logging.INFO, to_stream=False):
    """Configure root logging for one cron run.

    to_stream defaults to False: cron already captures stdout, and having BOTH a
    FileHandler and a StreamHandler is how officepi ended up with two identical
    77 MB log files (aranet_logger.log and cron.log) growing without rotation.
    """
    formatter = LocalTimeFormatter(LOG_FORMAT, tz=ZoneInfo(timezone))

    handlers = [logging.FileHandler(log_path)]
    if to_stream:
        handlers.append(logging.StreamHandler())
    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=handlers, force=True)
    return logging.getLogger("aranet")
