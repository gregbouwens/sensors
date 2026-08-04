"""Process exit codes, surfaced to Prometheus as aranet_run_exit_code.

These are a contract with observethis/config/alert_rules.yml -- the alerts key
off the numeric value to tell "the sensor went quiet" apart from "InfluxDB went
away". Renumbering them is a breaking change; add new codes at the end.
"""

EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_SENSOR_READ_FAILED = 2
EXIT_INFLUX_WRITE_FAILED = 3
