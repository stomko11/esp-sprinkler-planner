# Changelog

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
