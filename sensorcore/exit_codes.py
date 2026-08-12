"""Process exit codes, shared by every collector in this repo.

These are a contract with observethis/config/alert_rules.yml -- the alerts key
off the numeric value to tell "the sensor went quiet" apart from "InfluxDB went
away". Renumbering them is a breaking change; add new codes at the end.

The numbers are what the alerts read, so every collector uses the SAME four.
A second collector inventing its own numbering would mean each alert rule had
to know which job it was looking at before it could interpret the code.
"""

EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_SENSOR_READ_FAILED = 2
EXIT_SINK_WRITE_FAILED = 3
