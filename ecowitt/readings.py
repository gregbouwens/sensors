"""Value objects for the Ecowitt gateway, and the parser for its live payload.

The GW1200B returns every field as a STRING with the unit baked in::

    {"channel":"1","battery":"5","voltage":"1.56","humidity":"11%",
     "temp":"69.6","unit":"F","ec":"0 uS/cm"}

so all the interesting failure modes live in parsing. Two are worth naming:

* **The temperature unit is a gateway-wide display setting.** It arrives per
  channel as "F" or "C" and is honoured, never assumed -- reading a Celsius
  payload as Fahrenheit would turn 21 C into -6.1 C and poison the history
  without ever failing a run.
* **A dead probe simply vanishes from `ch_ec`.** Parsing only what is present
  would make a flat battery and a thriving plant produce identical, alert-free
  output. The snapshot therefore knows which channels were EXPECTED, and
  reports the difference.
"""

from dataclasses import dataclass, field

MIN_VALID_MOISTURE_PERCENT = 0
MAX_VALID_MOISTURE_PERCENT = 100
MIN_VALID_TEMPERATURE_C = -50.0
MAX_VALID_TEMPERATURE_C = 80.0
MIN_VALID_EC = 0.0

# A WH51-class soil probe reports a battery LEVEL of 0-5, not a percentage.
MAX_BATTERY_LEVEL = 5

UNIT_FAHRENHEIT = "F"
UNIT_CELSIUS = "C"
SUPPORTED_TEMPERATURE_UNITS = (UNIT_FAHRENHEIT, UNIT_CELSIUS)

KEY_SOIL_CHANNELS = "ch_ec"
KEY_AMBIENT = "wh25"

FIELD_CHANNEL = "channel"
FIELD_BATTERY = "battery"
FIELD_VOLTAGE = "voltage"
FIELD_MOISTURE = "humidity"
FIELD_TEMPERATURE = "temp"
FIELD_UNIT = "unit"
FIELD_EC = "ec"

FIELD_AMBIENT_TEMPERATURE = "intemp"
FIELD_AMBIENT_HUMIDITY = "inhumi"


class ReadingError(ValueError):
    """A reading came back implausible or unparseable -- treat it as a failed read."""


def c_to_f(celsius):
    return celsius * 9.0 / 5.0 + 32.0


def f_to_c(fahrenheit):
    return (fahrenheit - 32.0) * 5.0 / 9.0


def _strip_unit(raw):
    """Take the numeric head of a value like '11%', '0 uS/cm' or '69.6'."""
    text = str(raw).strip()
    for index, character in enumerate(text):
        if not (character.isdigit() or character in "+-."):
            return text[:index].strip()
    return text


def _number(raw, field_name, parse):
    """Parse a unit-suffixed numeric field, or fail with a message naming it.

    The gateway uses "--" for a field it has no value for. Coercing that to 0
    would write a fully-plausible-looking zero into a year of history, so it is
    rejected like any other garbage.
    """
    text = _strip_unit(raw)
    try:
        return parse(text)
    except (TypeError, ValueError) as error:
        raise ReadingError(
            f"Could not read {field_name} from {raw!r} (parsed {text!r})"
        ) from error


def _to_celsius(value, unit, channel_label):
    if unit not in SUPPORTED_TEMPERATURE_UNITS:
        raise ReadingError(
            f"{channel_label}: unrecognised temperature unit {unit!r} "
            f"(expected one of {', '.join(SUPPORTED_TEMPERATURE_UNITS)})"
        )
    return f_to_c(value) if unit == UNIT_FAHRENHEIT else value


@dataclass(frozen=True)
class ChannelReading:
    """One soil probe at one moment."""

    channel: int
    plant: str
    moisture_percent: int
    temperature_c: float
    ec_microsiemens_per_cm: float
    battery_level: int
    battery_volts: float

    @property
    def temperature_f(self):
        return c_to_f(self.temperature_c)

    def validate(self):
        """Raise ReadingError if this reading cannot be real."""
        label = f"channel {self.channel}"
        if not (
            MIN_VALID_MOISTURE_PERCENT
            <= self.moisture_percent
            <= MAX_VALID_MOISTURE_PERCENT
        ):
            raise ReadingError(
                f"{label}: implausible soil moisture {self.moisture_percent}% "
                f"(expected {MIN_VALID_MOISTURE_PERCENT}..{MAX_VALID_MOISTURE_PERCENT})"
            )
        if not MIN_VALID_TEMPERATURE_C <= self.temperature_c <= MAX_VALID_TEMPERATURE_C:
            raise ReadingError(
                f"{label}: implausible soil temperature {self.temperature_c} C "
                f"(expected {MIN_VALID_TEMPERATURE_C}..{MAX_VALID_TEMPERATURE_C})"
            )
        if self.ec_microsiemens_per_cm < MIN_VALID_EC:
            raise ReadingError(
                f"{label}: implausible EC {self.ec_microsiemens_per_cm} uS/cm "
                f"(expected >= {MIN_VALID_EC})"
            )
        if not 0 <= self.battery_level <= MAX_BATTERY_LEVEL:
            raise ReadingError(
                f"{label}: implausible battery level {self.battery_level} "
                f"(expected 0..{MAX_BATTERY_LEVEL})"
            )


@dataclass(frozen=True)
class AmbientReading:
    """The gateway's own built-in temperature/humidity sensor.

    Not soil data, but it is what drives the drying rate -- dry indoor air in
    winter empties a pot far faster than the same pot in August.
    """

    temperature_c: float
    humidity_percent: int

    @property
    def temperature_f(self):
        return c_to_f(self.temperature_c)


@dataclass(frozen=True)
class GatewaySnapshot:
    """Everything one poll of the gateway produced.

    `expected_channels` is what makes a missing probe visible: without it, a
    sensor whose battery died is simply absent from the payload and nothing
    downstream can tell that anything is wrong.
    """

    channels: tuple
    expected_channels: tuple
    ambient: AmbientReading | None
    # Carried so a channel that reported NOTHING can still be labelled with its
    # plant. "Monstera has stopped reporting" is actionable from a phone;
    # "channel 2 has stopped reporting" means walking the house to find out
    # which pot that is.
    channel_names: dict = field(default_factory=dict)

    def reading_for(self, channel):
        for reading in self.channels:
            if reading.channel == channel:
                return reading
        return None

    def plant_for(self, channel):
        """The configured name for a channel, reporting or not."""
        return self.channel_names.get(channel) or f"channel {channel}"

    def is_reporting(self, channel):
        return self.reading_for(channel) is not None

    @property
    def missing_channels(self):
        """Expected channels the gateway did not report. The alert-worthy set."""
        return tuple(
            channel
            for channel in self.expected_channels
            if not self.is_reporting(channel)
        )


def _parse_channel(entry, channel_names):
    channel = _number(entry.get(FIELD_CHANNEL), FIELD_CHANNEL, int)
    label = f"channel {channel}"

    temperature = _number(entry.get(FIELD_TEMPERATURE), f"{label} temperature", float)
    unit = str(entry.get(FIELD_UNIT, "")).strip().upper()

    reading = ChannelReading(
        channel=channel,
        plant=channel_names.get(channel) or f"channel {channel}",
        moisture_percent=_number(
            entry.get(FIELD_MOISTURE), f"{label} soil moisture", int
        ),
        temperature_c=_to_celsius(temperature, unit, label),
        ec_microsiemens_per_cm=_number(entry.get(FIELD_EC), f"{label} EC", float),
        battery_level=_number(entry.get(FIELD_BATTERY), f"{label} battery", int),
        battery_volts=_number(entry.get(FIELD_VOLTAGE), f"{label} voltage", float),
    )
    reading.validate()
    return reading


def _parse_ambient(payload):
    block = payload.get(KEY_AMBIENT) or []
    if not block:
        return None
    entry = block[0]
    if FIELD_AMBIENT_TEMPERATURE not in entry:
        return None

    temperature = _number(
        entry.get(FIELD_AMBIENT_TEMPERATURE), "ambient temperature", float
    )
    unit = str(entry.get(FIELD_UNIT, "")).strip().upper()
    return AmbientReading(
        temperature_c=_to_celsius(temperature, unit, "ambient"),
        humidity_percent=_number(
            entry.get(FIELD_AMBIENT_HUMIDITY), "ambient humidity", int
        ),
    )


def parse_livedata(payload, *, expected_channels, channel_names=None):
    """Turn one /get_livedata_info response into a validated GatewaySnapshot.

    An empty `ch_ec` is a valid snapshot with every channel missing, NOT an
    error: the gateway answered, which exonerates the network and points at the
    probes instead. The per-channel reporting metric carries that distinction.
    """
    channel_names = channel_names or {}
    entries = payload.get(KEY_SOIL_CHANNELS) or []

    readings = tuple(
        sorted(
            (_parse_channel(entry, channel_names) for entry in entries),
            key=lambda reading: reading.channel,
        )
    )

    return GatewaySnapshot(
        channels=readings,
        expected_channels=tuple(expected_channels),
        ambient=_parse_ambient(payload),
        channel_names=dict(channel_names),
    )
