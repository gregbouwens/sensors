# Idempotency of the collection jobs

Both collectors retry their InfluxDB write. This document records what that
retry does to the data, because the honest answer is *it depends on where the
timestamp comes from*, and getting it wrong produces duplicate history rather
than a visible failure.

This file was an empty placeholder until 2026-08-12, when the exact bug it was
meant to describe happened on the Ecowitt collector's first production run.

## The rule InfluxDB actually applies

A point is identified by **measurement + full tag set + field key + timestamp**.
Write the same combination twice and the second write *overwrites* the first —
one row, not two. Change any part of it, including the timestamp, and you get a
second row.

So a retried write is idempotent **only if the retry reuses the original
timestamp.**

## What happened on 2026-08-12

The Ecowitt collector's first run on officepi:

```text
14:20:23  INFO     Starting Ecowitt soil data collection...
14:20:33  WARNING  Attempt 1/3 to write to InfluxDB failed:
                   HTTPConnectionPool(host='docker20.dbmob.nl', port=8086):
                   Read timed out. (read timeout=9.995)
14:20:33  INFO     Retrying in 5.0 seconds...
14:20:43  INFO     Logged 2 of 2 expected probes (took 20.04s)
```

Exit code 0. The metrics file said the run succeeded. It had — twice:

```text
2026-08-12T21:20:23.702704Z  moisture=11  channel=1
2026-08-12T21:20:38.737927Z  moisture=11  channel=1     <-- same reading
```

**The first write did not fail.** InfluxDB accepted and committed it; the client
simply stopped waiting for the acknowledgement after 10 seconds. The retry then
built a fresh set of points stamped `time.now()` — 15 seconds later — which is a
different timestamp, therefore a different point, therefore a second row.

One poll of two probes became four rows of history, and nothing anywhere
reported a problem.

This is the mirror image of the Loki lesson in the homelab troubleshooting rules
("never treat *client sent it* as *store kept it*"). Here the client reported a
failure the store had already succeeded at. **A client-side timeout tells you
nothing about whether the server committed the write.**

### Why the write was slow at all

Worth ruling out, because "the network is flaky" would have been the easy story
and it is wrong. Measured immediately afterwards from officepi:

- `GET /health` → 5.7–7.6 ms, three times running
- three further collection runs → 0.26 s, 2.58 s, 3.09 s, no retries
- the Aranet4 job, running every 5 minutes for a year → **zero** `Read timed out`

The `sensors` bucket had never been written to. The 20-second run was one-time
first-write initialisation for a new measurement, not a network fault. It has
not recurred.

## The fix

The timestamp now belongs to the **snapshot**, set when the gateway is polled
(`EcowittGateway.read()`), not to the write attempt:

```python
read_at = self._clock()
payload = self._fetch(...)
return parse_livedata(..., read_at=read_at)
```

`InfluxSink.points_for()` derives every point's time from `snapshot.read_at`, so
attempt 2 and attempt 3 produce byte-identical line protocol and land on the
same point. Retrying is now safe by construction.

It is also the more truthful stamp. Under the old code a reading that took 20
seconds to write was recorded as having happened 20 seconds after the probe was
actually read.

Guarded by three tests in `tests/test_ecowitt_metrics.py`, all proven by
mutation — restoring `datetime.now()` in `_timestamp_for` turns all three red.

## Known gap: the Aranet4 collector still restamps

`aranet/sink.py` calls `self._now()` inside `write()`, so it has the same latent
bug. It has not fired: in a year of 5-minute runs officepi has logged no InfluxDB
read timeouts, and the one real incident (2026-08-03, office trunk re-terminated)
was a *connection* failure where nothing was ever committed — the retry was
correct and no duplicate was possible.

It is left alone deliberately rather than overlooked. Changing it means touching
a job that has been stable for a year, and the fix needs a `read_at` on `Reading`,
which `tests/test_sink.py` pins as a data-continuity contract. Worth doing; worth
doing on purpose, with its own PR.

**If you are reading this because you are about to add a third collector: put the
timestamp on the reading, at read time.**

## What is NOT idempotent, by design

- **The node_exporter textfile write.** Each run replaces `*.prom` wholesale via
  atomic `os.replace`. Re-running overwrites; it never appends. That is the
  intent — the file is current state, not history.
- **The success watermark.** `run_last_success_timestamp_seconds` deliberately
  carries forward across failures. See `sensorcore/textfile.py`.
