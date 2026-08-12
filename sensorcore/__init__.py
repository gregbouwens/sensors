"""Collector machinery shared by every sensor job in this repo.

Nothing in here knows what a CO2 sensor or a soil probe is. It is the part that
was identical between the Aranet4 job and the Ecowitt job, extracted so it is
written and tested once:

    exit_codes      the numeric contract with observethis' alert rules
    retry           retry helper for sensor reads and InfluxDB writes
    logging_setup   local-timezone logging for a cron run
    textfile        node_exporter textfile publishing + run-health invariants
    job             read -> write -> publish orchestration

Every module here is stdlib-only, so the whole control flow of any collector is
testable with nothing but pytest -- no Bluetooth adapter, no weather gateway
and no InfluxDB.

A collector supplies four things: a Config with the retry/textfile settings, a
sensor adapter with `.read()`, a sink adapter with `.write(payload)`, and a
TextfilePublisher that knows its own gauges.
"""
