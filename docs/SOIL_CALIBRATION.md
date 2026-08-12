# Calibrating the soil probes before trusting a "thirsty" alert

**Status 2026-08-12: not yet done. No moisture threshold alert should ship until
it is.** This file is the runbook.

## Why not just pick 20%?

Because we cannot currently tell these two apart:

- the soil genuinely is very dry, or
- the probes are reading low because of where they sit or how they are calibrated.

Both probes read **11% moisture and 0 µS/cm EC**, in two different pots, within
0.2 percentage points of each other. That is either a real and consistent
condition or a shared artifact, and guessing which one costs either a false alarm
while nobody is home or — much worse — silence while a plant dies.

The gateway's own calibration confirms the numbers are raw and untuned:

```json
{"id":"0x7284","ch":"1","soilVal":"11","nowAd":"738","minVal":"580","maxVal":"1620"}
{"id":"0x6F11","ch":"2","soilVal":"11","nowAd":"732","minVal":"573","maxVal":"1665"}
```

`minVal`/`maxVal` are the 0% and 100% endpoints, and they are **factory defaults**,
not measured against Tracy's actual soil. `nowAd` (738 and 732) is the real raw
reading, and the two probes genuinely agree — which is reassuring about the
hardware and says nothing about whether 11% means "thirsty".

**EC of 0 µS/cm is consistent with dry soil**, not a fault: electrical
conductivity needs moisture to conduct. Expect it to rise the moment a pot is
watered — which is itself one of the checks below.

## The runbook

### 1. Check the physical install first (5 minutes, do this before anything else)

The cheapest explanation is a bad install, so rule it out before collecting a
week of data that a bad install would invalidate.

- Probe prongs fully buried, all the way to the moulded shoulder. A prong half in
  air reads low forever.
- Probe in the **root zone**, not against the pot wall and not in the top crust
  that dries first.
- Nothing pushed so far it sits in the drainage layer.

### 2. Establish the WET endpoint (the discriminating test)

Water one pot thoroughly and watch what the number does. **This is the test that
distinguishes the two hypotheses**, and it settles the question in about an hour:

```bash
# before watering
curl -s http://10.20.10.156/get_livedata_info | python3 -m json.tool

# water thoroughly, then re-read every ~10 min for an hour
```

- **Moisture climbs sharply (11% → 40-60%+) and EC rises off 0** → the probes work
  and 11% was genuinely dry. Proceed to step 3.
- **Moisture barely moves** → the probe is not making soil contact, or the
  calibration endpoints are wrong for this soil. Go back to step 1; do not set a
  threshold on a probe that cannot see water.

Record the peak. That is the practical "just watered" value for **this pot and
this soil**, which is what the threshold has to be relative to.

### 3. Let it dry, and read the curve from real data

Leave it a week and watch the dry-down in Grafana
(see [QUERYING.md](QUERYING.md), first Flux query).

What to take from it:

- the **plateau** it settles toward when genuinely dry
- how many **days** wet → dry takes, per pot (they will differ)
- whether the two pots dry at similar rates

The trip is 2-4 weeks away, so there is room for a full cycle. A watering
interval measured in real days is what makes "will they last until we are home?"
answerable at all.

### 4. Only then, set the threshold

Sensible starting rule once you have real endpoints:

> alert at roughly **⅓ of the way from the dry plateau up to the watered peak**,
> and require it to hold for a few hours so a single odd reading cannot page.

Then translate to a Prometheus rule in `observethis/config/alert_rules.yml`,
with promtool tests, and both directions tested — it fires when it should, and
does **not** fire when the pot is fine.

### 5. Optionally, tell the gateway the real endpoints

The gateway will accept measured `minVal`/`maxVal` per channel, which makes the
percentage it reports meaningful rather than nominal. Not required — a threshold
against a consistent raw scale works fine — but it makes the numbers readable to
a human.

If you do change them, **note the date**: it changes the meaning of every
historical value, and a step change in the graph that nobody wrote down will look
like a real event later.

## What is already alerting, calibration or not

These need no threshold and are live now:

- `ecowitt_channel_reporting == 0` — a probe stopped answering (dead battery, out
  of range). **This is the failure that matters most while the house is empty**,
  and it needs no calibration to be correct.
- `ecowitt_battery_level <= 2` — battery getting low, on the 0-5 scale.
- collector staleness and exit codes — the pipeline itself broke.

Name the channels in `ECOWITT_CHANNELS` (`1:Fiddle Leaf Fig,2:Monstera`) and every
one of these alerts names the plant instead of a number.
