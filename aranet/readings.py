"""The Reading value object and its plausibility checks.

Thresholds are carried over unchanged from the original logger. They are not
"is the office comfortable" limits -- they reject the garbage an Aranet4 returns
when a BLE read comes back partial, which is the failure the retry loop exists
to paper over.
"""

from dataclasses import dataclass

MIN_VALID_CO2_PPM = 1
MIN_VALID_TEMPERATURE_C = -50.0
MAX_VALID_TEMPERATURE_C = 80.0


class ReadingError(ValueError):
    """A reading came back implausible -- treat it as a failed read."""


def c_to_f(celsius):
    """Convert Celsius to Fahrenheit."""
    return celsius * 9.0 / 5.0 + 32.0


@dataclass(frozen=True)
class Reading:
    co2_ppm: int
    temperature_c: float
    humidity_percent: int
    pressure_hpa: float
    battery_percent: int

    @property
    def temperature_f(self):
        return c_to_f(self.temperature_c)

    def validate(self):
        """Raise ReadingError if this reading cannot be real."""
        if self.co2_ppm < MIN_VALID_CO2_PPM:
            raise ReadingError(
                f"Implausible co2 reading: {self.co2_ppm} ppm "
                f"(expected >= {MIN_VALID_CO2_PPM})"
            )
        if not MIN_VALID_TEMPERATURE_C <= self.temperature_c <= MAX_VALID_TEMPERATURE_C:
            raise ReadingError(
                f"Implausible temperature reading: {self.temperature_c} C "
                f"(expected {MIN_VALID_TEMPERATURE_C}..{MAX_VALID_TEMPERATURE_C})"
            )

    @classmethod
    def from_aranet_current(cls, current):
        """Adapt the aranet4 library's current-readings object."""
        return cls(
            co2_ppm=int(current.co2),
            temperature_c=float(current.temperature),
            humidity_percent=int(current.humidity),
            pressure_hpa=float(current.pressure),
            battery_percent=int(current.battery),
        )
