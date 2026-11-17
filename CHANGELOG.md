# Changelog

## 0.10.2

- **Backup now holds the history and the switches:** statistics, watered minutes, last runs, learned flow,
  the log, temperature / rain logs and the Planner / Test mode switches are exported and restored.
  Skips, a pause and a run in progress are not.
- **Zone colours are kept:** a colour you never picked follows the zone's position; the export now pins
  the colour each zone shows, so it stays when zones come back in another order.
- **Restore asks for zones it could not match:** a backup zone that matches no valve by its entities
  (for example "Lawn South" after the ESP got "Lawn South 1" and "Lawn South 2") is offered in an extra
  step, with a guess by name. The chosen valve takes over that zone's settings and history.

## 0.10.1

- **Reconfigure** now offers zones that were added on the ESP since (shown as "New on the device") and
  keeps each existing zone's id by its entities, not by its position in the list. Before, a new valve
  could only be added by re-pointing an existing zone, which moved that zone's settings and history.
  Saved zones also take their current position from the ESP. The list text no longer shows a literal `\n\n`.
- **Action bar:** wraps instead of scrolling sideways (no clash with the HA swipe gesture). On narrow
  cards Quick run and Pause show only their icon; Skip shows the slot it skips.
- **Pause box:** Cancel and Pause stay on one line on a phone; "1 day" singular.
- **Skipped box:** new setting Settings > Planner > Skipped box: smart (default), always, never. With
  automatic weather, smart lists only the runs you skipped yourself.
- **Stats:** the per-zone table follows the Time / Water / Energy switch and has one extra column instead
  of up to six, so it fits a phone.
- The weather strip no longer makes the card scroll sideways on narrow phones.
- **Backup and restore:** Settings > Backup > Export settings saves all settings and the valve mapping to
  a JSON file. When the planner is added again, the first step takes that file: zones get their saved ids
  back (matched by ESP entities, then by name), so slots, days and minutes come back too. Anything that
  points at a zone that is gone is left out and listed in a notification.

## 0.10.0

- **Blockers** (Settings → Blockers): "when <entity> is on / off / is / is not / above / below",
  for every run, chosen slots or chosen zones. Then: skip, wait until it clears (at most N min, then
  skip or run), or ask in a notification (Run anyway / Wait 30 min / Skip, with a default after N
  min). Zone blockers leave those zones out. Optional: stop a run when the blocker turns on during
  it. Overview banner for a held run with the same buttons; `answer_blocker` service.
- **Pause** for 1 / 3 / 7 / 14 days or until a date (inclusive), Overview button and banner with
  Resume; paused runs are dimmed with ⏸; status `paused`; `pause` / `resume` services.
- **Log tab:** every run, skip, weather decision, blocker, alarm and pause with its reason, minutes,
  water and energy, grouped by day, filter All / Runs / Skips & weather / Alarms.
- **Repairs:** controller missing or offline > 1 h, weather entity missing, notify target missing
  appear under Settings → Repairs.
- **Diagnostics download** (config, plan, recent log, states; nothing secret).
- The log shows which Home Assistant user started, stopped, skipped, paused or resumed, also when answered from a notification.
- Zone settings no longer scroll sideways.

## 0.9.0

- **Weekly average** (Settings → Weather): the season level from the average daily maximum of
  N measured days back and N forecast days ahead, mapped through bands you edit (e.g. below
  15 °C → 50 %, above 32 °C → 150 %), plus an optional correction for today's deviation from the
  average (capped). Replaces the per-degree rule while on; rain, wind and frost still apply. The
  daily maximum is logged by the planner and read from the recorder (14 days) at start. A live
  line shows what it gives right now.
- **Leak alarm** (Settings → Meters, needs a flow sensor): water flowing while no zone waters,
  above a minimum flow for N minutes in a row. Quiet N minutes before and after runs, optional
  stricter night window, a "valve did not close" check after each run, "That's me" snooze and
  an optional automatic pump off. Overview banner with the same buttons; `leak_snooze` service;
  notifications `leak` and `valve_stuck`.
- **Cycle & soak** (Settings → Zones): a zone's minutes split into 2-4 passes with a minimum soak
  time between them. Per slot: other zones run while one soaks (default, almost no extra time) or
  the whole slot pauses. ESP order / reverse stays; finish-by slots still end on time; weather and
  skips apply to the whole slot run; one started / finished notification per slot run; manual runs
  water in one go. Timelines show the passes, run lists "pass 1/2".

## 0.8.2

- Overview: current weather only in the chips. The "Weather" heading no longer repeats the
  temperature and the rain; the temperature chip falls back to the weather entity when there is
  no temperature sensor, and the rain chip shows the tracked rain of the window ("3.2 mm / 24 h").

## 0.8.1

- Forecast on the Overview: the day marks line up on every day, also on days without rain.

## 0.8.0

- **Setup finds the zones on its own and confirms them in one step:** after the controller step a
  "Found N zones" page lists every zone in ESP order. Submit takes them all; "check each" goes
  through them one by one; "add a valve that was not found" maps an extra one. No more ticking
  "add another" for every zone. Same in Reconfigure.
- **Discovery understands more names:** accents are ignored (Záhony = Zahony), Slovak, Czech,
  German and Polish words for duration / enable / multiplier / repeat / reverse / standby / main
  switch, and names without any known word are paired by name (a switch, the same name plus one
  word for the enable switch, and a number).
- By zone view on narrow screens: day pills with two letters and a smaller layout, so the days
  fit the card instead of running off the side.

## 0.7.6

- Weather suggestions: the run and the suggested action in bold, the full reason below in smaller
  text; every suggestion has the same height, also without a reason.
- "Zones today" on the Overview is collapsible (list / tiles toggle stays in its header).
- Long zone names no longer wrap in section headers (By zone view, Settings → Zones).

## 0.7.5

- Weather suggestions on the Overview take one line each: run, action, reason (shortened) and
  round green ✓ / red ✕ buttons on the right. Same buttons in the day panel.
- Bulb and label in suggestion marks are vertically centred.

## 0.7.4

- Minutes fields step by whole minutes with the arrows (decimals can still be typed).
- Slot zone rows stay on one line with long names and own days; long slot names in the
  Overview "Run slot" selector are shortened instead of widening the bar.

## 0.7.3

- The pump power and water flow chips on the Overview are hidden while idle (flow below
  0.5 L/min, pump below 20 W) and appear live as soon as the pump runs.

## 0.7.2

- **Test mode (dry run) simulates the whole run:** started, every zone change on the real timing
  (pump delay, valve overlap), finished / stopped, skips - with the same notifications as a real
  run, titled "🧪 Test:". Nothing is switched: not the ESP, not the pump. Statistics are not
  touched. The Overview shows the simulated zone and a "Test" chip.
- Overview: Stop sits in the header row of the Now box (no longer over the zone name); between
  zones it shows "Switching zone…", at the end "Finishing…", after Stop "Stopping…" instead of
  "Starting…".
- Live chips for **pump power in kW** and **water flow in L/min** when those meters are set.
- Starting a run asks "Start watering now?" (the dry-run wording is gone).

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
