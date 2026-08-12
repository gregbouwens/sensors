# How to query the sensor data

There are **two** stores, deliberately, and which one you want depends on the
question you are asking.

| | InfluxDB | Prometheus |
| --- | --- | --- |
| Holds | full history, every 5 min, forever | the **latest** value only |
| Written by | the collector, directly | node_exporter scraping `*.prom` |
| Use it for | "how has this pot dried out over 3 weeks?" | alerting, "is it OK right now?" |
| Query language | Flux | PromQL |
| Where | `docker20.dbmob.nl:8086`, bucket `sensors` | `docker21.dbmob.nl:9090` |

The short version: **Grafana for looking, Prometheus for alerting, InfluxDB for
history.**

## The data model

Bucket `sensors`, two measurements:

**`ecowitt_soil_readings`** — one row per probe per poll

| | |
| --- | --- |
| tags | `channel` (1-8), `plant`, `device`, `location` |
| fields | `moisture` (%), `temperature_f`, `ec` (µS/cm), `battery_level` (0-5), `battery_volts` |

**`ecowitt_ambient_readings`** — the gateway's own sensor, one row per poll

| | |
| --- | --- |
| tags | `device`, `location` |
| fields | `temperature_f`, `humidity` (%) |

`plant` is set from `ECOWITT_CHANNELS` in `.env`, so naming a channel there makes
every query and every alert read in plain English instead of channel numbers.

## Grafana (what you actually want most of the time)

<http://docker21.dbmob.nl:3000> → Explore → InfluxDB datasource → bucket `sensors`.

Paste a Flux query from below, or use the query builder. For a dashboard panel
of soil moisture over time, the first query is the one you want.

## Flux, against InfluxDB

**Soil moisture for every plant over the last 7 days** — the calibration and
dry-down curve, and the main dashboard panel:

```flux
from(bucket: "sensors")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "ecowitt_soil_readings")
  |> filter(fn: (r) => r._field == "moisture")
  |> aggregateWindow(every: 30m, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value", "plant"])
```

**Latest reading for every plant, all fields** — the "how are they right now?"
query:

```flux
from(bucket: "sensors")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "ecowitt_soil_readings")
  |> last()
  |> keep(columns: ["_time", "plant", "channel", "_field", "_value"])
```

Verified output, 2026-08-12:

```text
channel   plant        moisture  last reading
1         channel 1    11%       2026-08-12T21:37:03Z
2         channel 2    11%       2026-08-12T21:37:03Z
```

**How fast is a pot drying?** Percentage points lost per day — this is what
turns into a useful "will it last until we get home?" number:

```flux
from(bucket: "sensors")
  |> range(start: -3d)
  |> filter(fn: (r) => r._measurement == "ecowitt_soil_readings" and r._field == "moisture")
  |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
  |> difference()
  |> keep(columns: ["_time", "_value", "plant"])
```

**Soil moisture against room humidity**, for the question "does the house drying
out explain the pots drying out?":

```flux
soil = from(bucket: "sensors")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "ecowitt_soil_readings" and r._field == "moisture")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)

air = from(bucket: "sensors")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "ecowitt_ambient_readings" and r._field == "humidity")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)

union(tables: [soil, air])
```

### From the command line

The token lives only in officepi's `.env`, so the quickest one-liner runs there:

```bash
ssh officepi 'set -a; . ~/repos/sensors/.env; set +a;
curl -s -H "Authorization: Token $INFLUXDB_TOKEN" \
     -H "Content-Type: application/vnd.flux" -H "Accept: application/csv" \
     --data-binary "from(bucket: \"sensors\") |> range(start: -1h)
       |> filter(fn: (r) => r._measurement == \"ecowitt_soil_readings\")
       |> last()" \
     "$INFLUX_URL/api/v2/query?org=$INFLUX_ORG"'
```

## PromQL, against Prometheus

Prometheus holds only the newest value, because it scrapes the `.prom` file the
collector rewrites each run. That makes it the right place for *alerting* and the
wrong place for history.

```promql
# current soil moisture, per plant
ecowitt_soil_moisture_percent

# a probe that was EXPECTED but did not answer -- 0 means silent
ecowitt_channel_reporting == 0

# probe batteries getting low (0-5 scale, NOT a percentage)
ecowitt_battery_level <= 2

# the collector itself has not reached InfluxDB in over 30 minutes
(time() - ecowitt_run_last_success_timestamp_seconds) > 1800

# which half broke: 2 = gateway unreachable, 3 = InfluxDB unreachable
ecowitt_run_exit_code
```

### Why `ecowitt_channel_reporting` exists

It is the one metric worth understanding before you write an alert. When a
probe's battery dies, the gateway simply **stops listing that channel** — it does
not report an error. So `ecowitt_soil_moisture_percent{channel="2"}` would just
stop existing, and:

> a rule like `ecowitt_soil_moisture_percent < 20` can never fire on a series
> that is not there.

The plant would go dry in complete silence. `ecowitt_channel_reporting` is
published for every channel listed in `ECOWITT_CHANNELS` whether it answered or
not, so there is always a series to alert on.

**Corollary:** dropping a channel from `ECOWITT_CHANNELS` silently stops watching
that plant. That setting is the watchlist.

## Sanity checks

```bash
# what the collector last published
ssh officepi 'cat /var/lib/node_exporter/textfile_collector/ecowitt.prom'

# what it did last run
ssh officepi 'tail -20 ~/repos/sensors/ecowitt_logger.log'

# run it by hand
ssh officepi 'cd ~/repos/sensors && sensors_env/bin/python3 ecowitt_logger.py; echo "exit=$?"'

# read the gateway directly, bypassing everything above
curl -s http://10.20.10.156/get_livedata_info | python3 -m json.tool
```
