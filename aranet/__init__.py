"""Aranet4 -> InfluxDB logging job for the office desk sensor on officepi.

Layout deliberately separates a dependency-free core from the two thin adapters
that touch the outside world, so the core is testable on any box with nothing
but pytest:

    config      environment-driven settings           (stdlib only)
    readings    Reading value object + validation     (stdlib only)
    retry       shared retry helper                   (stdlib only)
    metrics     node_exporter textfile collector      (stdlib only)
    job         run orchestration                     (stdlib only)

    sensor      Aranet4 over BLE     -- imports aranet4/bleak
    sink        InfluxDB write path  -- imports influxdb_client
"""
