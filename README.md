# sensors

Aranet4 CO2/temperature/humidity/pressure logging for the office desk, running
on **officepi.dbmob.nl** (Raspberry Pi 3B, Debian 12 aarch64) and writing to
**InfluxDB on docker20.dbmob.nl:8086** (`influx-homelab`).

A cron job reads the sensor over Bluetooth LE every 5 minutes and writes one
point to the `aranet4_readings` measurement.

## Layout

The core is dependency-free and unit-tested; the two modules that touch the
outside world are thin adapters, so the whole control flow can be exercised
without a Bluetooth adapter or a database.

| Module | Responsibility | Imports |
| --- | --- | --- |
| `aranet/config.py` | env-driven settings, explicit validation | stdlib |
| `aranet/readings.py` | `Reading` value object + plausibility checks | stdlib |
| `aranet/retry.py` | shared retry helper | stdlib |
| `aranet/metrics.py` | node_exporter textfile publishing | stdlib |
| `aranet/job.py` | run orchestration + exit-code contract | stdlib |
| `aranet/exit_codes.py` | the contract with observethis alerts | stdlib |
| `aranet/logging_setup.py` | local-timezone logging | stdlib |
| `aranet/sensor.py` | Aranet4 over BLE | `aranet4`, `bleak` |
| `aranet/sink.py` | InfluxDB write path | `influxdb_client` |
| `aranet_logger.py` | entrypoint — wires the real adapters together | all |

`aranet_recovery.py` and `aranet_import_csv.py` are standalone one-shot
backfill tools; they predate this structure and are not part of the cron path.

## Monitoring

Health is reported to Prometheus through **node_exporter's textfile
collector**, the same pattern paperless uses for `vision-ocr`. Every run
atomically rewrites
`/var/lib/node_exporter/textfile_collector/aranet.prom`:

| Metric | Meaning |
| --- | --- |
| `aranet_run_last_timestamp_seconds` | when the last run finished, pass or fail |
| `aranet_run_last_success_timestamp_seconds` | when data last reached InfluxDB |
| `aranet_run_exit_code` | 0 ok · 1 config · 2 sensor · 3 influx |
| `aranet_run_duration_seconds` | wall-clock of the last run |
| `aranet_sensor_read_ok` / `aranet_influx_write_ok` | which half of the pipeline worked |
| `aranet_co2_ppm`, `aranet_temperature_fahrenheit`, `aranet_humidity_percent`, `aranet_pressure_hpa`, `aranet_battery_percent` | last successful reading |

Two invariants are load-bearing and have tests:

- **A failed run carries the previous success timestamp forward.** Resetting it
  would re-arm the staleness alert on every failure, so a permanently broken
  job would never look stale and the alert would never fire.
- **A job that has never succeeded omits the watermark** rather than writing 0,
  which would read as "last succeeded in 1970" and page the moment the
  collector is switched on.

Alerts live in `observethis/config/alert_rules.yml` (`sensors_alerts`), with
promtool tests in `observethis/config/tests/sensors_test.yml`. The exporter is
enabled on officepi by `ansible-me/roles/node_exporter` (textfile collector).

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

TDD is mandatory here (see the global rule). The tests are also verified by
mutation: breaking an invariant in the production code must turn its test red.

## Deploy

officepi is **pull-only** — never edit files on the host. Author on the Mac,
commit, push, then on officepi:

```bash
# ssh -A is REQUIRED: officepi has no GitHub key of its own (~/.ssh holds only
# authorized_keys), so the pull authenticates through the Mac's forwarded
# 1Password SSH agent. Without -A the pull fails with the misleading
# "Please make sure you have the correct access rights and the repository
# exists" — which reads like the repo is gone, not like an auth problem.
ssh -A officepi 'git -C ~/repos/sensors pull --ff-only'
ssh officepi 'cd ~/repos/sensors && sensors_env/bin/pip install -r requirements.txt'
```

Verify the deploy landed — a successful pull is not proof the job still runs:

```bash
ssh officepi 'cd ~/repos/sensors && sensors_env/bin/python3 aranet_logger.py; echo "exit=$?"'
ssh officepi 'cat /var/lib/node_exporter/textfile_collector/aranet.prom'
```

Cron line: `deploy/crontab.example`.
Log rotation: `deploy/logrotate/aranet-logger` (install instructions in the file).

## Secrets

`.env` on officepi holds the InfluxDB API token; it is gitignored and lives
only on that host. See `.env.example` for the full list of settings.

This repo predates the homelab's 1Password render-secrets pattern
(`observethis/scripts/render-secrets.sh`). Migrating the token to a rendered
secret is worthwhile but has not been done.

## History

- **2026-08-04** — split into the package above, instrumented for Prometheus,
  fixed the retry bug below, bounded the logs, added CI + branch protection.
- **2026-08-03** — the office trunk cat6 was re-terminated and officepi's switch
  was unplugged for 45 minutes. Nine consecutive runs failed. `HostDown` paged
  correctly, but the job's own retry loop only retried `InfluxDBError`, so DNS
  failures re-raised on the first attempt instead of being retried. Fixed, with
  a regression test (`tests/test_retry.py`).
- **2025-08** — original single-file logger; edited in place on the Pi.
