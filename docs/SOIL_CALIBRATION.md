# Calibrating the soil probes before trusting a "thirsty" alert

**Status 2026-08-12: step 2 is DONE — the probes are proven good and the dry
endpoint is real. Step 3 (the dry-down curve) is in progress.** Still no
moisture threshold alert until it finishes. This file is the runbook.

## Result of step 2 (2026-08-12, 15:12)

Tracy watered the larger of the two plants — channel 1 — and the question this
document was written to answer settled itself in a single 5-minute poll:

```text
time      ch1 moisture  ch1 EC      ch2 moisture  ch2 EC     (ch2 = control)
22:07     11%           0 uS/cm     11%           0 uS/cm
22:12     64%           70 uS/cm    11%           0 uS/cm
```

Three things fell out of that at once:

- **The probes work.** 11% → 64% in one interval.
- **EC rose off zero**, which is the independent confirmation. Conductivity
  needs moisture to conduct, so it cannot rise unless water actually reached the
  probe. Two different physical quantities moved together, which no calibration
  artifact would produce.
- **The unwatered pot did not move.** Channel 2 stayed at 11% with EC 0
  throughout — an unplanned but perfect control, ruling out shared drift, a
  gateway-wide artifact, or a units bug.

**So 11% was genuine dryness, not a bad install and not a factory-calibration
artifact.** The hypothesis below was real and is now closed.

### What the settling curve says

Twenty minutes later channel 1 read **48%** and falling. The 64% spike is
saturation at the moment of watering, not the number to calibrate against:

> **Use the SETTLED value after the pot has drained (roughly an hour), not the
> peak.** The peak is water still on its way through, and anchoring a threshold
> to it would set every trigger too high.

### Measured endpoints so far

| | Channel 1 (larger plant) | Channel 2 (control) |
| --- | --- | --- |
| dry plateau | 11% (stable ~1h before watering) | 11% |
| saturation peak | 64%, EC 70 µS/cm | — |
| 20 min after | 48% | — |
| settled / field capacity | **still measuring** | — |
| days wet → dry | **still measuring** | — |

Step 3 is now just watching. The two remaining unknowns — the settled wet value
and how many days the dry-down takes — are exactly what turns a threshold from a
guess into a number, and what makes *"will they last until we are home?"*
answerable.

## Why we did not just pick 20%

Kept because it is the reasoning, and because the same question will come up for
the next probe added. Before the watering above, we could not tell these apart:

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

### 2. Establish the WET endpoint (the discriminating test) — DONE 2026-08-12

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

> alert at roughly **⅓ of the way from the dry plateau up to the SETTLED wet
> value**, and require it to hold for a few hours so a single odd reading cannot
> page.

With channel 1's dry plateau at 11%, that puts the threshold somewhere in the
low-to-mid 20s once the settled value is known — but do not hard-code that from
this paragraph. Read it off the curve, and set it **per channel**: the two pots
are different sizes and will not dry at the same rate. `ECOWITT_CHANNELS` names
them, so the rule can say the plant's name.

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
