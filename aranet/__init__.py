"""Aranet4 -> InfluxDB logging job for the office desk sensor on officepi.

The collector machinery that is not specific to the Aranet4 -- retry, logging,
exit codes, textfile publishing and the run orchestration -- lives in
`sensorcore` and is shared with the Ecowitt soil collector. What remains here
is only the Aranet4 itself:

    config      environment-driven settings           (stdlib only)
    readings    Reading value object + validation     (stdlib only)
    metrics     which gauges the Aranet4 publishes    (stdlib only)
    job         binds sensorcore.job to those gauges  (stdlib only)

    sensor      Aranet4 over BLE     -- imports aranet4/bleak
    sink        InfluxDB write path  -- imports influxdb_client
"""
