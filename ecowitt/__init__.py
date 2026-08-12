"""Ecowitt GW1200B gateway -> InfluxDB soil-moisture collector.

Polls the gateway's local HTTP API for every paired soil probe and records
moisture, temperature, EC and battery. Same shape as the Aranet4 job: a
dependency-free core plus two thin adapters, all driven by sensorcore.

    config      environment-driven settings           (stdlib only)
    readings    value objects + payload parsing       (stdlib only)
    metrics     which gauges the gateway publishes    (stdlib only)

    gateway     the local HTTP API  -- imports requests
    sink        InfluxDB write path -- imports influxdb_client

The gateway lives on the Arlo (untrusted IoT) VLAN. Traffic to it is allowed;
traffic FROM it into the homelab is not. That one-way rule is why this is a
poller and not a receiver for the gateway's own "Customized upload" push mode.
"""
