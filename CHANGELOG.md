# Changelog

## 0.7.1

- Unticking a zone in a slot keeps its minutes and days (stored as switched off); ticking it again
  brings them back instead of a default. Minutes and days can be set for a zone before it is
  switched on. Switched-off zones are dimmed and not counted in the slot header.

## 0.7.0

- **Days per zone in a slot:** each zone in a slot follows the slot's weekdays ("slot days") or
  has its own days, which replace the slot's days for that zone - it can also run on a day the
  slot has off. ↺ goes back to the slot's days. In an every-N-days slot own days narrow it.
  So Monday morning can water 3 zones and Tuesday morning 5 with one Morning slot.
- **Slots tab "By slot / By zone":** the same schedule seen the other way around - per zone, in
  which slots, how many minutes and on which days.

## 0.6.1

- Weather decisions only count zones that follow the weather (zone "follow weather" on and slot
  "adjust by weather" on). A run where only some zones follow the weather shows e.g. "✕ 3/5" with
  the zones that still run, instead of a plain ✕ while the run still started. A run where no zone
  follows the weather gets no weather mark at all.
- Notification variables `{{ water_m3 }}` / `{{ expected_water_m3 }}` (already in 0.5.3) and the
  tracked rain of 0.6.0.

## 0.6.0

- **Rain that fell is tracked by the planner:** any rain counter works (event, daily, weekly,
  monthly, yearly, total, rolling 24 h). Every rise of the counter is logged, resets are handled,
  and the rain of the last N hours (new setting, default 24 h) counts. A daily sensor that reset at
  midnight no longer hides last evening's rain from the morning run. The last 72 h are read from
  the recorder when the sensor is picked or Home Assistant starts.

## 0.5.4

- Weather settings explain each sensor: what "rain fallen" is used for (mm in the next 24 h, event
  rain / last 24 h / daily - not weekly, monthly, yearly or total counters), wind and gusts,
  "raining now" (binary or mm/h). A warning appears when the picked rain sensor looks like a
  growing total or a rate.

## 0.5.3

- Notification variables `{{ water_m3 }}` and `{{ expected_water_m3 }}` next to the litre ones.

## 0.5.2

- **Buttons on Android / iOS for any recipient:** each recipient chip shows how it is sent
  (Android, iOS or text only) and can be set by hand. Auto detection only knows the
  `notify.mobile_app_*` services; a notify group or your own notify service around the app was
  sent as text only, so the buttons were dropped. A hint in Settings names such recipients.
- **Usage in notifications:** `{{ water_l }}`, `{{ energy_kwh }}`, `{{ cost }}`, `{{ avg_flow }}`
  for finished (and stopped) runs, `{{ expected_water_l }}` for planned / started / skipped
  (from each zone's usual flow). A dash when there is no meter.
- **Slow flow drop** (clogging filter): each zone learns its normal flow from its first 5 runs;
  when the median of the last 5 runs is 15 % (settable) below it, `flow_drift` notifies once.
  Stats shows "last runs / normal (±%)" per zone with a reset button; `reset_flow` service.
- **Clear statistics** button (with confirmation) and `clear_stats` service.
- Notification variable `{{ zone_count }}`: number of zones in the run (all run events).
- **Duplicate a slot:** button in the slot editor. The copy goes right below the original, switched
  off (so nothing waters twice) and opened for editing; Save to keep it.

## 0.5.1

- **Controller offline / removed is clearly shown:** red banner on every tab (offline since when,
  which entities), red status chip and header icon, next run struck through. The status sensor
  has the new state `offline` with `offline_since`, `missing_entities`, `unavailable_entities`.
  New notifications `offline` (after 3 minutes, so short ESP reconnects stay quiet) and `online`
  (off by default).
- **One mark per day** in Week, the slot preview and the forecast: the result when all runs of the
  day end the same (✓, ✕, −50 %), otherwise e.g. "1/2 ✕", plus one dot per run (filled = applied,
  ring = suggestion, max 6). Click it for the day's runs with Skip / Accept / Dismiss / Undo, also
  on the Week and Slots tabs.

## 0.5.0 - first public release

Plans and runs irrigation on an ESPHome `sprinkler:` controller. Dry run is on after install.

- **Planner:** slots that start at or finish by a time, sunrise or sunset (with offset); weekdays
  or every N days; per-slot zones and minutes; ESP order or reverse; merging of close slots;
  per-run, per-day and ESP limits. Each run is one ESP cycle (enable switches, durations,
  reverse, multiplier 1, main switch), with a watchdog and restore afterwards.
- **Weather:** off, suggest (Accept / Dismiss) or automatic. Skip on rain (fallen + forecast),
  wind, gusts, frost or rain right now; adjust minutes by temperature. Zones can ignore the
  weather (greenhouse, indoor).
- **Pump:** on before, off after, warning when it is off.
- **Notifications:** any notify services or entities, editable texts per event, Android / iOS
  buttons (Stop, Skip, Pump on, Accept, Dismiss), test per event and per recipient.
- **Card** (served by the integration): Overview with forecast and day panel, Week, Stats
  (time, water, pump energy, costs, 12-month heatmap), Slots editor with live preview,
  Settings. Compact card. English and Slovak.
- **Statistics** from the valve switches, with optional water and pump meters; flow warnings.
- Services for everything the card does; Reconfigure keeps slots and history.
