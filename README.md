# sensors

Environmental sensor collection for the homelab, running on
**officepi.dbmob.nl** (Raspberry Pi 3B, Debian 12 aarch64) and writing to
**InfluxDB on docker20.dbmob.nl:8086** (`influx-homelab`).

Two collectors, both on a 5-minute cron:

| Collector | Reads | Over | Bucket | Entrypoint |
| --- | --- | --- | --- | --- |
| **Aranet4** | CO2, temperature, humidity, pressure at the office desk | Bluetooth LE | `aranet4` | `aranet_logger.py` |
| **Ecowitt GW1200B** | soil moisture, soil temperature, EC and battery for each houseplant probe, plus gateway ambient temp/humidity | HTTP, across the VLAN boundary | `sensors` | `ecowitt_logger.py` |

**To query any of it, see [docs/QUERYING.md](docs/QUERYING.md).**

## Layout

`sensorcore` is the machinery neither collector owns; each collector package is
only what is specific to its device. The core is dependency-free, so the whole
control flow of either job runs in tests with no Bluetooth adapter, no weather
gateway and no database.

| Module | Responsibility | Imports |
| --- | --- | --- |
| `sensorcore/config.py` | shared settings + all-at-once validation | stdlib |
| `sensorcore/retry.py` | retry helper for reads and writes | stdlib |
| `sensorcore/textfile.py` | node_exporter publishing, labels, run invariants | stdlib |
| `sensorcore/job.py` | read → write → publish orchestration | stdlib |
| `sensorcore/exit_codes.py` | the numeric contract with observethis | stdlib |
| `sensorcore/logging_setup.py` | local-timezone logging | stdlib |
| `aranet/readings.py`, `aranet/metrics.py`, … | the Aranet4's own settings, values and gauges | stdlib |
| `aranet/sensor.py` | Aranet4 over BLE | `aranet4`, `bleak` |
| `aranet/sink.py` | InfluxDB write path | `influxdb_client` |
| `ecowitt/readings.py`, `ecowitt/metrics.py`, … | the gateway's payload parsing and gauges | stdlib |
| `ecowitt/gateway.py` | the gateway's local HTTP API | stdlib (`urllib`) |
| `ecowitt/sink.py` | InfluxDB write path, N points per run | `influxdb_client` |

A collector supplies four things: a Config, a sensor adapter with `.read()`, a
sink adapter with `.write(payload)`, and a `TextfilePublisher` that knows its own
gauges.

`aranet_recovery.py` and `aranet_import_csv.py` are standalone one-shot backfill
tools; they predate this structure and are not on the cron path.

## The Ecowitt gateway

Lives at `10.20.10.156` on the **Arlo (untrusted IoT) VLAN**. officepi can reach
it; **it cannot reach the homelab.**

That one-way rule is the whole architecture. The gateway supports a "Customized
upload" push mode, which would be less work — and cannot be used, because a push
would have to cross the blocked direction. So this is a poller, and the untrusted
device is never able to initiate anything.

The gateway has **no authentication**: every endpoint answers unauthenticated,
including `/get_network_info`, which returns the Arlo SSID's password
base64-encoded. The VLAN placement contains this (anything that can read it is
already on Arlo and already has that PSK), but the same surface also means
anything on Arlo can reconfigure or factory-reset the gateway.

Useful endpoints, all plain GET, all returning JSON as `text/html`:

| Endpoint | Returns |
| --- | --- |
| `/get_livedata_info` | **the one the collector uses** — live readings, all channels |
| `/get_sensors_info?page=N` | paired sensors, IDs, battery, RSSI |
| `/get_cli_soilad` | raw ADC values and calibration endpoints per channel |
| `/get_version`, `/get_units_info` | firmware and display units |

Two traps the parser handles, both proven by mutation tests:

- **Every value is a string with the unit baked in** (`"11%"`, `"0 uS/cm"`), and
  `"--"` means "no value" — coerced to `0` it would write a plausible-looking lie
  into history, so it is rejected.
- **The temperature unit follows a gateway-wide display setting**, arriving per
  channel as `F` or `C`. It is honoured, never assumed; reading a Celsius payload
  as Fahrenheit turns 21 °C into −6.1 °C and poisons the history without ever
  failing a run.

### `ECOWITT_CHANNELS` is the watchlist

When a probe's battery dies, the gateway **stops listing that channel** rather
than reporting an error. So the config declares which channels are *expected*,
and `ecowitt_channel_reporting` is published for each of them — 1 answered, 0
silent. A threshold rule can only fire on a series that exists.

**Dropping a channel from this setting silently stops watching that plant.**

Naming the channels (`ECOWITT_CHANNELS=1:Fiddle Leaf Fig,2:Monstera`) makes every
metric, log line and alert say the plant's name instead of a number.

## Monitoring

Health is reported to Prometheus through **node_exporter's textfile collector**.
Each run atomically rewrites its own file in
`/var/lib/node_exporter/textfile_collector/` — `aranet.prom`, `ecowitt.prom`.

Both publish the same run-health metrics under their own prefix:
`{prefix}_run_last_timestamp_seconds`, `_run_last_success_timestamp_seconds`,
`_run_exit_code` (0 ok · 1 config · 2 sensor · 3 influx), `_run_duration_seconds`,
`_sensor_read_ok`, `_influx_write_ok`.

Ecowitt adds per-channel gauges labelled `channel` and `plant`:
`ecowitt_channel_reporting`, `ecowitt_soil_moisture_percent`,
`ecowitt_soil_temperature_fahrenheit`, `ecowitt_soil_ec_microsiemens_per_cm`,
`ecowitt_battery_level` (0-5, **not** a percentage), `ecowitt_battery_volts`, plus
unlabelled `ecowitt_ambient_temperature_fahrenheit` / `_ambient_humidity_percent`.

Three invariants are load-bearing and have tests:

- **A failed run carries the previous success timestamp forward.** Resetting it
  would re-arm the staleness alert on every failure, so a permanently broken job
  would never look stale and the alert would never fire.
- **A job that has never succeeded omits the watermark** rather than writing 0,
  which would read as "last succeeded in 1970" and page the moment the collector
  is switched on.
- **HELP/TYPE are declared once per metric name, not per sample.** A duplicate
  HELP line makes node_exporter reject the *whole file* — which, since both
  collectors share one scrape, would take the Aranet4's metrics down alongside
  the soil probes'.

Alerts live in `observethis/config/alert_rules.yml` (`sensors_alerts`), with
promtool tests in `observethis/config/tests/sensors_test.yml`.

**No soil-moisture threshold alert exists yet, on purpose** — see
[docs/SOIL_CALIBRATION.md](docs/SOIL_CALIBRATION.md).

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

TDD is mandatory here (see the global rule). Tests are also verified by
**mutation**: breaking an invariant in the production code must turn its test
red, with a message describing the real bug. The commit history records which
mutations were run for each invariant.

## Deploy

officepi is **pull-only** — never edit files on the host.

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
ssh officepi 'cd ~/repos/sensors && sensors_env/bin/python3 ecowitt_logger.py; echo "exit=$?"'
ssh officepi 'cat /var/lib/node_exporter/textfile_collector/ecowitt.prom'
```

Cron lines: `deploy/crontab.example` (the two jobs are staggered so they do not
both wake a Pi 3B on the same minute).
Log rotation: `deploy/logrotate/aranet-logger` — covers both logs.

## Secrets

`.env` on officepi holds the InfluxDB API token, shared by both collectors; it is
gitignored and lives only on that host. See `.env.example` for the full list, and
note that the **bucket is per-collector** — both jobs read the same file, so a
single `INFLUX_BUCKET` would put soil readings in with a year of CO2 history.

This repo predates the homelab's 1Password render-secrets pattern
(`observethis/scripts/render-secrets.sh`). Migrating the token to a rendered
secret is worthwhile but has not been done.

## History

- **2026-08-12** — added the Ecowitt soil collector; extracted `sensorcore` so
  both jobs share one tested core (behaviour equivalence verified byte-for-byte,
  which caught a HELP string the tests did not). Fixed a duplicate-write bug
  found on the new collector's first production run — a client-side timeout on a
  write InfluxDB had already committed, retried with a fresh timestamp, wrote the
  reading twice. See [docs/IDEMPOTENCY_ANALYSIS.md](docs/IDEMPOTENCY_ANALYSIS.md).
- **2026-08-04** — split into the package structure above, instrumented for
  Prometheus, fixed the retry bug below, bounded the logs, added CI + branch
  protection.
- **2026-08-03** — the office trunk cat6 was re-terminated and officepi's switch
  was unplugged for 45 minutes. Nine consecutive runs failed. `HostDown` paged
  correctly, but the job's own retry loop only retried `InfluxDBError`, so DNS
  failures re-raised on the first attempt instead of being retried. Fixed, with a
  regression test (`tests/test_retry.py`).
- **2025-08** — original single-file logger; edited in place on the Pi.
