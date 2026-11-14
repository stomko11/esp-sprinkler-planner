# ESP Sprinkler Planner

Home Assistant integration + dashboard card that plans and runs irrigation on top of an
[ESPHome sprinkler controller](https://esphome.io/components/sprinkler/). The ESP keeps
running the valves; the planner decides **when**, **which zones**, **how long** and **in what
order** - without input_booleans, scripts or automations.

Status: **0.5** - planner, card, notifications, pump, weather, quick run, statistics. Dry run
is on after install: nothing is sent to the ESP until you switch it off.

[![Open your Home Assistant instance and add this repository to the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=stomko11&repository=esp-sprinkler-planner&category=integration)

## Install

**Marketplace (Home Assistant 2026.11+) or HACS**

1. Settings → Marketplace (or HACS) → ⋮ → **Custom repositories** →
   `https://github.com/stomko11/esp-sprinkler-planner`, type **Integration** - or use the button above.
2. Open **ESP Sprinkler Planner** → **Download**, then restart Home Assistant.
3. Settings → Devices & services → **Add integration** → ESP Sprinkler Planner.

Updates appear under Settings → Updates with the release notes.

**Manual:** copy `custom_components/esp_sprinkler_planner` into `<config>/custom_components/`
and restart.

The dashboard card is served by the integration itself - no resource to add.

Requirements: Home Assistant 2026.8 or newer, an ESPHome device with a `sprinkler:` controller.

---

## 1. Zones

- Add the integration, pick the ESPHome device. It lists the sprinkler controller's entities:
  per valve the **enable switch**, **valve switch** and **run duration number**; for the
  controller the **main switch**, **multiplier**, **reverse**, **standby**, **auto advance**,
  **repeat** (whatever the device exposes).
- Each valve is mapped to a **logical zone**: name, icon, colour. Names on the ESP do not
  matter - another user's valves map the same way.
- **Order = the order the valves are defined on the ESP.** The ESP sprinkler controller runs
  the enabled valves in that order, or reversed with its reverse switch; the planner works
  with exactly that.
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
  - **order**: ESP order, or **⇅ reverse**
  - weather rules: inherit the global ones, or override / switch off per slot
  - enabled on/off
- **How a run is started:** the planner writes the durations into the ESP duration numbers,
  turns the run's zones' enable switches on and all others off, sets the reverse switch and
  the multiplier to 1 (durations are already final), then starts **one cycle**. The ESP does
  the rest - sequence, valve overlap, timing - and finishes even if Home Assistant drops out.
  Durations go back to the previous values afterwards (configurable).

## 3. Merging and conflicts

The controller runs one valve at a time, so slots that would overlap or sit close together
become one **run**. Configurable:

- **Merge window**: two runs are merged when the gap between the first one's end and the
  next one's start is N minutes (e.g. 60) or less, or when they overlap. The check is repeated
  on the merged result, so a chain of slots merges only as long as each next gap still fits.
- **One cycle**: the merged run contains all zones of both, in ESP order, in the direction
  of the part with more zones (equal: the earlier one). Timing: if either part is
  "finish by", the merged run finishes by the earliest finish-by time; otherwise it starts at
  the earlier start.
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

## Using 0.1

### Install and set up

1. Copy `custom_components/esp_sprinkler_planner` to `<config>/custom_components/`, restart.
2. Settings → Devices & services → Add integration → **ESP Sprinkler Planner**.
3. Pick the ESPHome device. Controller entities are proposed from the names; check them.
   **Valve overlap** is the `valve_overlap` from the ESPHome YAML (it is not exposed as an
   entity), used for timing only.
4. One step per detected valve: name, enable switch, run duration number, valve switch
   (optional), **position on the ESP** (0 = first), use / skip. "Add another" maps a valve that
   was not detected.

The planner starts with **dry run on**: it plans, logs and fires events, but sends nothing to
the ESP. Turn `switch.<name>_planner_dry_run` off only when you want it to really water.

### Entities

| entity | |
|---|---|
| `sensor.<name>_planner_next_run` | timestamp of the next run; attributes: end, zones (name, minutes), slots, merged, reverse, notes, conflicts |
| `sensor.<name>_planner_status` | idle / scheduled / running / dry_run / disabled / error; attributes: active run, the service calls of the current (dry) run, last event |
| `switch.<name>_planner_planner_enabled` | off = scheduled runs are skipped |
| `switch.<name>_planner_dry_run` | on = nothing is sent to the ESP |

Event `esp_sprinkler_planner_event` with `type`: `started`, `finished`, `stopped`, `skipped`
(with `reason`), `dry_run` (with the calls it would make), `error`, `skip_set`.

### Weather

Settings tab, **Weather**. Mode `off`, `suggest` or `auto`:

- Source: a `weather.*` entity (hourly forecast preferred, daily as fallback), optional rain
  sensor (mm that already fell) and temperature sensor. Units are converted (°F, in, mph, m/s).
- **Skip** a run when fallen + expected rain (next N h, only hours with probability ≥ X %)
  reaches the limit, at strong wind, or below a frost temperature at the start (beyond the
  hourly forecast, morning runs use the daily low).
- **Adjust** the minutes: 100 % at a daily maximum of `base_temp`, ± `per_degree` % per
  degree, less rain shortens proportionally, clamped to min / max %. Applied per day to the
  slots that use the multiplier.
- `suggest`: runs within the horizon get a suggestion (card + notification with
  Accept / Dismiss buttons). Nothing changes until accepted.
- `auto`: applied directly; the weather is read again at the run start. "Run anyway" undoes it.

**Which rain sensor goes where**

| setting | what it is used for | use | do not use |
|---|---|---|---|
| Rain sensor (fallen) | rain of the last N hours (default 24), added to the forecast for runs in the next 24 h | any rain counter in mm: event, daily, weekly, monthly, yearly, total, rolling 24 h | rates (mm/h) |
| Raining now | skip a run that starts within the hour while it rains | binary rain sensor, rain rate in mm/h (> 0 = raining) | amounts in mm |

The planner logs every rise of the counter itself and handles resets, so a daily sensor that
reset at midnight still counts last evening's 40 mm for the morning run. When you pick a sensor it
also reads the last 72 h from the recorder. The card warns when the picked sensor is a rate.

### Quick run, skips

**Quick run** on the Today tab: tick zones, set minutes, ESP order or reverse, run once.
Service `quick_run` with `zones: [{zone, minutes}]`. Skipped runs (by you or by the weather)
are listed with **Undo** / **Run anyway** (service `unskip`).

### Statistics and meters

Stats tab: this week / month / year / all time, a chart by day / week / month / year
(watering time, water, pump energy) and a per-zone table (time, valve openings, litres,
average and usual flow, kWh, average power). Data is kept for 3 years.

Optional meters (Settings): water flow (L/min, m³/h), water meter total (L, m³), pump power
(W, kW), pump energy total (kWh, Wh). Totals are used when present, otherwise the rate is
integrated while a zone is open. A zone whose flow differs from its usual flow by more than
X % raises the `flow_warning` notification (leak or blocked valve). Service `get_stats`.

### Zones, language, notifications

- Zones are configured in Settings → Zones: name, colour, optional **icon** (`mdi:*`, shown in
  the zone colour), use, **follow weather** (off for a greenhouse or indoor zone: never
  shortened, lengthened or skipped; in a weather-skipped run only these zones still run),
  max per run / day.
- Overview tab: now / next run (with the weather mark and zones), action bar (Stop, Quick run,
  Skip, Run slot), live sensor chips, forecast, today's timeline, zones as a compact list or
  tiles (toggle, or `zones: list | tiles` in the card YAML). A progress bar fills while a run is on.
- Weather sensors (all optional): temperature, humidity, wind, gusts, rain fallen, raining now
  (binary sensor or mm/h). Raining now, gusts and wind are checked for runs starting within
  the hour.
- Prices per m³ and kWh (Settings → Meters) show costs on the Stats tab, next to a
  12-month heatmap.
- Zone colours: preset swatches plus the colours already used by other zones.
- Compact card: `type: custom:esp-sprinkler-planner-compact` - progress ring, next run,
  live sensors, Stop / Quick run / Skip.
- Week chart: the past 7 days (watered) and the next 7 (planned).
- Card header: integration icon, editable name (Settings → Planner), and the master switch
  that turns the planner on / off.
- Week and slot preview show per run: ✓ as planned, ✕ skipped, ±50 % adjusted; a `?` means
  a suggestion waiting for Accept / Dismiss.
- Statistics count every opening of a mapped valve switch, also ones started outside the
  planner (ESP button, other automations). A valve already open at an HA restart is counted
  from when it opened.
- **Language** auto / English / Slovensky: card, default notification texts and buttons,
  weather reasons. Changed notification texts stay as you wrote them.
- Recipients: any number of notify services or notify entities (chips; add any
  `notify.*` by name, e.g. two phones). The send icon on a chip tests just that recipient; the
  send icon on an event tests it with the current (even unsaved) texts.
- Default titles start with an emoji per event; on Android each event also has its own
  status-bar icon and colour. Changed texts stay as written.
- Week / preview marks: filled ✕ or -50 % = applied; dashed with a bulb = only a suggestion.
- Click a forecast day on Overview to see its runs with Skip / Undo / Run anyway, or Accept /
  Dismiss for a suggestion (service `skip_run` skips one run by key). Clicking a dashed
  suggestion mark in Week / preview accepts it.
- Your own skips (grey ✕) undo on click. **Clear all** in the Skipped section (service
  `clear_skips`) undoes every skip you set and forgets every weather answer.
- Stats: totals are folded into one line; period is a dropdown; the heatmap fits the card width.
- Clicking an answered mark (filled = accepted, ✓ = dismissed) takes the answer back; the
  run is undecided again (service `answer_suggestion` with `reset: true`).
- Weather → "When the forecast changes after I answered": **keep** (default, the answer and
  its minutes stay as they were) or **follow** (an accepted run follows the new forecast; if the
  suggested action changes, e.g. -50 % becomes skip, you are asked again).
- Slot editor explains start / finish, offset (minutes before / after the time, sunrise or
  sunset) and "adjust by weather" (off = always the exact minutes).
- The master switch stops the schedule; manual and quick runs still work. When off, the next
  run is struck through.
- Every notification event has editable title and message (templates), own recipients
  (any number of `notify.*` services) and buttons. New events: `suggestion`, `weather`,
  `flow_warning`.

### Changing the valve mapping

Settings → Devices & services → ESP Sprinkler Planner → ⋮ → **Reconfigure**. Same steps as setup,
pre-filled. Zones keep their ids, so slots, settings and history stay. A removed valve is
dropped from the slots.

### Card

The integration serves its own card - no resource to add. On any dashboard add a manual card:

```yaml
type: custom:esp-sprinkler-planner-card
# entry_id: ...   only with more than one planner
# tab: today      start tab: today | week | slots | zones | settings
# title: Garden
```

- **Today**: what runs now (zone, until when), next run, Stop / Skip next / Run slot now,
  today's timeline (runs coloured per zone, merged runs outlined, sunrise / sunset / now
  lines), per zone minutes today, last and next run.
- **Week**: seven timelines and the list of runs with notes (caps, merges, shifts).
- **Slots**: add / edit / delete slots - start at or finish by a time / sunrise / sunset
  with offset, weekdays or every N days, zones with their own minutes, reverse, multiplier,
  enabled. The preview (timelines, runs, conflicts) updates while you edit, before saving.
- **Zones**: name, colour, use / disable, max per run and per day, last 7 days of watering,
  run now.
- **Settings**: planner enabled, dry run, merge mode / window / same zone, pump, notification
  targets and every event (title, message, targets, buttons, test).

Changes are kept as a draft until **Save**; invalid values are rejected with the reason in
the save bar. Saving needs an admin user. With dry run off, "run now" asks for confirmation.

### Configuration by service

`esp_sprinkler_planner.configure` replaces `zones`, `slots` and/or `settings`:

```yaml
action: esp_sprinkler_planner.configure
data:
  zones:                      # optional, per zone id (zone_1 ... as created in the flow)
    zone_5: {name: "Lawn West", enabled: true, max_per_run: 45, max_per_day: 90}
  slots:
    - id: morning
      name: Morning
      reverse: true            # ESP order reversed
      anchor: {mode: start, ref: time, at: "05:00"}      # or mode: finish; ref: sunrise / sunset
      days: [0, 1, 2, 3, 4, 5, 6]                       # weekdays 0=Mon; or every_n_days: 2 + every_n_from
      use_multiplier: true
      zones:
        - {zone: zone_5, minutes: 15}
        - {zone: zone_1, minutes: 60, days: [0, 3]}     # optional own days inside the slot
    - id: evening
      name: Evening
      anchor: {mode: finish, ref: sunset, offset: 180}  # finish 3 h after sunset
      zones: [{zone: zone_5, minutes: 5}]
  settings: {merge_mode: window, merge_window: 60, same_zone: longer}
```

Invalid input is rejected with a message saying exactly what is wrong. Other services:
`get_plan` (response: runs and conflicts for N days), `run_slot`, `run_zone`, `stop`,
`skip_next`, `replan`.

### Per-zone entities and buttons

Per zone: `sensor.<name>_planner_<zone>_next_run`, `..._last_run` (with minutes) and
`..._minutes_today` (actually watered, measured from the valve switch; attribute
`last_7_days`). `sensor.<name>_planner_active_zone` shows the valve that is open now
(attributes: since, planned minutes, until). Buttons: **Stop**, **Skip next run**.

Watering time is measured from the valve switches whoever started them, so manual runs count
too. History is kept 14 days.

### Notifications

```yaml
action: esp_sprinkler_planner.configure
data:
  notifications:
    targets: [notify.mobile_app_pixel, notify.mobile_app_iphone]   # default for every event
    platforms: {notify.my_telegram: other}                         # optional override
    events:
      planned:      {enabled: true, lead: 30}                      # 30 min before a run
      started:      {message: "{{ zone_list }} until <b>{{ end_time }}</b>"}
      zone_changed: {enabled: true, targets: [notify.mobile_app_pixel]}
      finished:     {enabled: true}
      skipped:      {enabled: true}
```

Events: `planned`, `started`, `zone_changed`, `finished`, `skipped`, `stopped`, `error`,
`pump_off`, `dry_run`. Per event: `enabled`, `targets` (else the global ones), `title`,
`message` (templates) and `actions` (`stop`, `skip`, `pump_on`). Defaults: started,
finished, skipped, stopped, error and pump_off on; planned, zone_changed and dry_run off.
Nothing is sent until `targets` is set.

Variables: every event has `planner`, `slots`, `zones`, `zone_list`, `start_time`,
`end_time`, `duration_min`, `day`, `source`; plus `lead` (planned), `zone`,
`zone_minutes` (zone_changed), `actual_minutes` (finished), `reason` (skipped, stopped,
error), `pump` (pump_off), `calls` (dry_run).

The platform of a `notify.mobile_app_*` target is read from the Companion app registration:
Android gets icon, channel `Irrigation`, simple HTML and at most 3 buttons; iOS gets plain
text and the buttons; any other notify service gets title and plain message. Buttons work from
both apps (`mobile_app_notification_action` / `ios.notification_action_fired`). All
notifications of one planner use the same tag, so the next one replaces the previous one.

`esp_sprinkler_planner.test_notification` sends one event with example values.

### Pump

```yaml
  pump: {entity: switch.well_pump, auto_on: true, auto_off: true, delay: 10, warn_if_off: true}
```

`auto_on`: switched on before the valves, then `delay` seconds (counted in the run timing).
`auto_off`: switched off after the run when the planner turned it on (or the "Turn pump ON"
button did). Without `auto_on`, `warn_if_off` sends `pump_off` with a Turn pump ON button
when a run starts with the pump off. Any switch / input_boolean / light / fan entity.

### What a run does on the ESP

Multiplier → 1, repeat → 0, each zone's duration into its duration number, enable switches off
for the other zones and on for the run's zones, reverse switch, main switch on. The ESP runs
the cycle. When the main switch goes off, durations, enable switches and multiplier are put
back (option). Before starting it checks: main switch not already on, standby off, every entity
available. A **watchdog** turns the main switch off when the run is still on N minutes (option,
default 10) after its planned end. After a Home Assistant restart an active run is picked up
again.

Options: restore after a run, watchdog margin, valve overlap.

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

## Development

```
python3 -m unittest discover -s tests -v
```

The tests use only the standard library (pytest runs them too).

Reference material for the first user (current automations, scripts, ESPHome config,
dashboard) stays outside this repo.
