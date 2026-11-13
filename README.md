# ESP Sprinkler Planner

Home Assistant integration + dashboard card that plans and runs irrigation on top of an
[ESPHome sprinkler controller](https://esphome.io/components/sprinkler/). The ESP keeps
running the valves; the planner decides **when**, **which zones**, **how long** and **in what
order** - without input_booleans, scripts or automations.

Status: **design** (nothing implemented yet). This file is the spec we agree on first.

- Home Assistant 2026.11+, installed through HACS (custom repository)
- Domain: `esp_sprinkler_planner`

---

## 1. Zones

- Add the integration, pick the ESPHome device. It lists the sprinkler controller's entities:
  per valve the **enable switch**, **valve switch** and **run duration number**; for the
  controller the **main switch**, **multiplier**, **reverse**, **standby**, **auto advance**,
  **repeat** (whatever the device exposes).
- Each valve is mapped to a **logical zone**: name, icon, colour, default position in the
  order. Names on the ESP do not matter - another user's valves map the same way.
- **Disable a zone** without touching the ESP config: it is never enabled or run, and is
  hidden from planning. Unmapped valves are ignored.
- **Limits per zone** (safety + bounds for suggestions): max minutes **per run** and
  **per day**. The ESP's `max_value` is the hard ceiling.

## 2. Slots

- Default four: **Morning, Midday, Afternoon, Evening**; rename, add, delete.
- A slot has:
  - **time anchor**: `start at 05:30`, or `finish by 08:15 / sunrise ± X / sunset ± X`
    (start is computed backwards, see 4.)
  - **days**: weekdays, or every N days
  - **zones** in the slot, each with its **own duration** for this slot
    (Lawn West 15 min in the morning, 5 min in the evening) and optionally its own days
  - **order**: default zone order, **⇅ reverse**, or custom (drag)
  - weather rules: inherit the global ones, or override / switch off per slot
  - enabled on/off
- Before a run the planner writes the durations into the ESP duration numbers, sets the
  enable switches and the reverse switch, then starts the cycle. Durations go back to the
  previous values afterwards (configurable).

## 3. Merging and conflicts

The controller runs one valve at a time, so slots that would overlap or sit close together
become one **run**. Configurable:

- **Merge window**: runs starting within N minutes (e.g. 60) of each other, or overlapping,
  are merged.
- **Placement**: the run with fewer zones joins the bigger one on the side where it was
  planned - earlier → added at the start, later → added at the end. Equal size: earlier
  slot's order first.
- **Alternatives**: "never merge, shift the later run" or "merge only on overlap".
- **Same zone in both**: longer duration (default) / sum / keep as two runs.
- Anything the planner cannot resolve inside the limits is a **conflict**: shown in the card,
  optional notification.

## 4. Timing

- Run length = Σ(zone duration × multiplier) + valve overlap (read from config, default 5 s)
  + pump start delay.
- "Finish by" anchors start the run that much earlier; the start is recomputed when the
  multiplier changes (heat) up to the moment the run starts.
- Sunrise / sunset from `sun.sun` or HA location.

## 5. Weather (all optional - features appear only for what is configured)

- Sources: a `weather.*` entity (forecast: rain, max temperature), and/or sensors: rain
  (mm + period), temperature (average or current), humidity.
- Rules:
  - **skip on rain**: measured in the last X h and/or forecast in the next Y h, above Z mm
  - **multiplier by temperature**: a scale, e.g. 25 °C → ×1.2, 30 °C → ×1.5, 33 °C → ×1.8
  - humidity correction (optional)
- **Suggestions** (e.g. "3 days above 30 °C - add an Afternoon run for the lawns",
  "raise multiplier to ×1.5"):
  - per rule: **propose** (card banner and/or notification with Accept / Dismiss) or
    **apply automatically**
  - automatic changes are always bounded by the zone limits (per run / per day) and global
    limits (max multiplier, max extra runs per day)
  - accepted / applied suggestions can be temporary (until weather normalises) or permanent

## 6. Pump and safety (each part optional)

- Pump switch: auto on before a run (with delay), off after; keep on when merged runs are
  less than X min apart; warn (notification with button) if the pump is off at start.
- Guards: standby switch, "no zones enabled → don't start", **watchdog** (run longer than
  computed + margin → stop), recovery after an HA restart mid-run (state read back from the
  ESP, no double start).
- **Tap left open**: flow above X l/min for Y min within Z min of the start → stop, notify.
- Manual: run a zone / run a slot now, skip next run, stop, pause / resume (if the ESP
  exposes it).

## 7. Notifications

- Delivered through Home Assistant `notify.*` services; you pick which (one or more per event).
- Events, each on/off on its own: run planned (X min before), started, zone changed,
  finished, skipped (rain / standby / no zones / disabled), stopped (tap / watchdog / manual),
  pump off at start, conflict, suggestion.
- Per event: services, title and message (templates). The editor only offers variables that
  exist for the configuration: zones, start/end, multiplier, temperature, rain; **water used**
  only with a meter / flow sensor; **pump energy** only with a power sensor.
- Defaults reproduce the current notifications.
- Platform limits (handled by the defaults, documented in the editor):
  - action buttons: Android max **3**, iOS more but the first ones show without expanding
  - `notification_icon`, `channel`, `color` and HTML formatting: **Android only**;
    iOS gets plain text
  - iOS actions need no categories with the current Companion app; `uri` actions work on both

## 8. Entities (for any dashboard)

Next run (timestamp), finish time, status (idle / planned / running / paused / skipped),
active zone, remaining time, skip reason, multiplier in use; per zone: next run, last run,
minutes today / this week, water used (if available). Switches: planner enabled, per slot
enabled. Buttons: run now, skip next, stop.

## 9. Card

- **Today / week timeline**: runs as bars per zone, merged runs marked, conflicts, sunrise /
  sunset, now-line; **watered hours** per zone as a heat-strip ("sprinkler hours").
- **Zones**: status, remaining time, run once, today's minutes, limits.
- **Slot editor**: anchor, days, zones with durations, order (reverse / drag).
- **Weather & suggestions**: current inputs, active rules, pending suggestions
  (Accept / Dismiss).
- **Graphs** (later): minutes per zone per day, water used, multiplier vs. temperature.
- Optional header row with extra entities (pressure, flow, pump power…).

---

## Architecture

```
custom_components/esp_sprinkler_planner/
  __init__.py          setup, websocket API for the card, frontend registration
  config_flow.py       pick ESPHome device, map valves → zones
  planner.py           pure logic: slots → runs (merge, order, timing) - unit tested
  weather.py           rule evaluation, suggestions - unit tested
  executor.py          drives the ESP (durations, enables, reverse, start), pump, watchdog
  notify.py            events → notify services, templates, platform limits
  sensor.py switch.py button.py
  store.py             config + state in .storage (no helpers)
  frontend/esp-sprinkler-planner-card.js   built from /card
card/                  card source (Lit + TypeScript)
tests/                 pytest for planner / weather / notify
```

The planner and weather logic are plain Python with no HA dependency, so the merge and
timing rules can be tested on their own.

## Milestones

1. Planner core + tests (slots, merge, ordering, timing, limits)
2. Integration: config flow, zone mapping, storage, executor (start a run on the ESP)
3. Entities + notifications
4. Card: zones, slot editor, timeline
5. Weather rules + suggestions
6. Graphs, polish, HACS release

Reference material for the first user (current automations, scripts, ESPHome config,
dashboard) stays outside this repo.
