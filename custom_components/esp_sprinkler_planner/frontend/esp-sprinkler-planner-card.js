/* ESP Sprinkler Planner card.
 *
 *   type: custom:esp-sprinkler-planner-card
 *   entry_id: <optional, only with more than one planner>
 *   tab: today | week | stats | slots | zones | settings   (optional start tab)
 *   title: <optional>
 *
 * Served by the integration (no resource needed). Plain custom element, no build step.
 */
const DOMAIN = "esp_sprinkler_planner";
const SWATCHES = ["#1f6fd1", "#0aa5a5", "#147a44", "#7cb342", "#c47a00", "#ff5722", "#b3261e", "#8e24aa", "#5c6bc0", "#795548", "#9e9e9e", "#ffd600"];
const PALETTE = ["#4e9cf5", "#2fbf71", "#f5a524", "#e5484d", "#a970ff", "#16c1c8", "#ff7ab6", "#c3e14b"];
const ICONS = ["mdi:sprinkler", "mdi:sprinkler-variant", "mdi:water", "mdi:water-outline", "mdi:watering-can", "mdi:flower",
  "mdi:flower-tulip", "mdi:sprout", "mdi:grass", "mdi:tree", "mdi:pine-tree", "mdi:palm-tree", "mdi:leaf", "mdi:fruit-cherries",
  "mdi:fruit-grapes", "mdi:carrot", "mdi:corn", "mdi:greenhouse", "mdi:home", "mdi:home-variant", "mdi:fence", "mdi:pool",
  "mdi:dog-side", "mdi:car", "mdi:compass-outline", "mdi:pipe", "mdi:pipe-valve", "mdi:numeric-1-circle", "mdi:numeric-2-circle",
  "mdi:numeric-3-circle", "mdi:numeric-4-circle", "mdi:numeric-5-circle", "mdi:numeric-6-circle", "mdi:numeric-7-circle", "mdi:numeric-8-circle"];
const WX_ICON = { "clear-night": "night", cloudy: "cloudy", exceptional: "alert-circle-outline", fog: "fog", hail: "hail",
  lightning: "lightning", "lightning-rainy": "lightning-rainy", partlycloudy: "partly-cloudy", pouring: "pouring", rainy: "rainy",
  snowy: "snowy", "snowy-rainy": "snowy-rainy", sunny: "sunny", windy: "windy", "windy-variant": "windy-variant" };

// ------------------------------------------------------------------ language
const SK = {
  "Today": "Dnes", "Overview": "Preh\u013ead", "Skip": "Presko\u010di\u0165", "Run slot": "Spusti\u0165 slot", "Live": "Teraz",
  "humidity": "vlhkos\u0165", "wind": "vietor", "gusts": "n\u00e1razy", "raining": "pr\u0161\u00ed", "dry": "sucho",
  "Humidity sensor": "Senzor vlhkosti", "Wind sensor": "Senzor vetra", "Gust sensor": "Senzor n\u00e1razov vetra",
  "Raining now (binary or mm/h)": "Pr\u00e1ve pr\u0161\u00ed (bin\u00e1rny alebo mm/h)", "skip at gusts \u2265": "presko\u010di\u0165 pri n\u00e1razoch \u2265",
  "Live sensors": "Aktu\u00e1lne senzory", "Prices": "Ceny", "water per m\u00b3": "voda za m\u00b3", "energy per kWh": "energia za kWh",
  "Cost": "N\u00e1klady", "Last 12 months": "Posledn\u00fdch 12 mesiacov", "less": "menej", "more": "viac",
  "Zone colours in use": "Pou\u017eit\u00e9 farby z\u00f3n", "Click to accept": "Kliknut\u00edm prijme\u0161", "Skipped by you. Click to undo.": "Presko\u010dil si. Kliknut\u00edm vr\u00e1ti\u0161.",
  "Undo skip": "Zru\u0161i\u0165 presko\u010denie", "Clear all": "Vymaza\u0165 v\u0161etko", "Undo all your skips and forget all weather answers?": "Zru\u0161i\u0165 v\u0161etky tvoje presko\u010denia a zabudn\u00fa\u0165 v\u0161etky odpovede na po\u010dasie?",
  "Totals": "S\u00fahrny", "per day": "po d\u0148och", "per week": "po t\u00fd\u017ed\u0148och", "per month": "po mesiacoch", "per year": "po rokoch", "Accepted. Click to take back.": "Prijat\u00e9. Kliknut\u00edm vr\u00e1ti\u0161.",
  "Dismissed: runs as planned. Click to take back.": "Zamietnut\u00e9: be\u017e\u00ed pod\u013ea pl\u00e1nu. Kliknut\u00edm vr\u00e1ti\u0161.",
  "Take back accept": "Zru\u0161i\u0165 prijatie", "Take back dismiss": "Zru\u0161i\u0165 zamietnutie",
  "When the forecast changes after I answered": "Ke\u010f sa predpove\u010f po odpovedi zmen\u00ed",
  "keep my answer as it was": "necha\u0165 moju odpove\u010f, ako bola", "follow the new forecast, ask again if it changes": "riadi\u0165 sa novou predpove\u010fou, pri zmene sa op\u00fdta\u0165 znova", "Close": "Zavrie\u0165", "No runs on this day.": "V tento de\u0148 ni\u010d nebe\u017e\u00ed.",
  "Click a day for its runs.": "Klikni na de\u0148 pre jeho behy.", "adjust by weather": "upravi\u0165 pod\u013ea po\u010dasia", "Planner off": "Pl\u00e1nova\u010d vypnut\u00fd", "missing": "ch\u00fdba", "Remove": "Odstr\u00e1ni\u0165",
  "Suggestion (not applied): {0}": "N\u00e1vrh (nepou\u017eit\u00fd): {0}", "Time": "\u010cas", "Energy": "Energia", "average / usual": "priemer / be\u017en\u00fd",
  "+ add notify service": "+ prida\u0165 notify slu\u017ebu", "Send test to {0}": "Posla\u0165 test na {0}", "Sent to {0}": "Odoslan\u00e9: {0}",
  "Pick at least one recipient.": "Vyber aspo\u0148 jedn\u00e9ho pr\u00edjemcu.", "A notify service looks like notify.mobile_app_phone": "Notify slu\u017eba vyzer\u00e1 ako notify.mobile_app_telefon",
  "Any notify service or notify entity, e.g. notify.mobile_app_stefan and notify.mobile_app_wife. Each chip sends a test to just that one.": "\u013dubovo\u013en\u00e1 notify slu\u017eba alebo entita, napr. notify.mobile_app_stefan a notify.mobile_app_manzelka. Ka\u017ed\u00fd \u010dip po\u0161le test len jemu.", "left": "zost\u00e1va", "list": "zoznam", "tiles": "dla\u017edice", "Week": "T\u00fd\u017ede\u0148", "Stats": "\u0160tatistiky", "Slots": "Sloty", "Zones": "Z\u00f3ny", "Settings": "Nastavenia",
  "Idle": "Ne\u010dinn\u00e9", "Scheduled": "Napl\u00e1novan\u00e9", "Running": "Be\u017e\u00ed", "Dry run": "Sk\u00fa\u0161ka", "Disabled": "Vypnut\u00e9", "Error": "Chyba",
  "DRY RUN": "SK\u00da\u0160KA", "Nothing is sent to the ESP": "Do ESP sa ni\u010d neposiela", "planner off": "pl\u00e1nova\u010d vypnut\u00fd",
  "Loading\u2026": "Na\u010d\u00edtavam\u2026", "Now": "Teraz", "Starting\u2026": "Sp\u00fa\u0161\u0165am\u2026", "until {0}": "do {0}", "run ends {0}": "koniec behu {0}",
  "Nothing running": "Ni\u010d nebe\u017e\u00ed", "Next run": "\u010eal\u0161\u00ed beh", "Stop": "Zastavi\u0165", "Skip next": "Presko\u010di\u0165 \u010fal\u0161\u00ed",
  "Run slot now": "Spusti\u0165 slot", "Quick run": "R\u00fdchly beh", "Zones today": "Z\u00f3ny dnes",
  "{0} min watered today, {1} min still planned today": "dnes {0} min polievan\u00e9, e\u0161te {1} min napl\u00e1novan\u00e9",
  "next run": "\u010fal\u0161\u00ed beh", "Sunrise": "V\u00fdchod", "Sunset": "Z\u00e1pad", "merged": "zl\u00fa\u010den\u00e9", "reverse": "opa\u010dne",
  "No runs in the next 7 days.": "\u017diadne behy v najbli\u017e\u0161\u00edch 7 d\u0148och.", "Minutes per day": "Min\u00faty za de\u0148",
  "(watered / planned)": "(polievan\u00e9 / napl\u00e1novan\u00e9)", "Next 7 days": "Najbli\u017e\u0161\u00edch 7 dn\u00ed", "Run details": "Detaily behov",
  "planned": "napl\u00e1novan\u00e9", "Finish by": "Skon\u010di\u0165 do", "Start": "\u0160tart", "Start at": "Za\u010da\u0165 o", "sunrise": "v\u00fdchod slnka",
  "sunset": "z\u00e1pad slnka", "time": "\u010das", "every {0} days": "ka\u017ed\u00fdch {0} dn\u00ed", "every day": "ka\u017ed\u00fd de\u0148", "{0} zones": "{0} z\u00f3n",
  "enabled": "zapnut\u00e9", "Name": "N\u00e1zov", "offset": "posun", "min": "min", "Weekdays": "Dni v t\u00fd\u017edni", "Every N days": "Ka\u017ed\u00fdch N dn\u00ed",
  "every": "ka\u017ed\u00fdch", "days from": "dn\u00ed od", "reverse ESP order": "opa\u010dn\u00e9 poradie ESP", "use multiplier": "pou\u017ei\u0165 n\u00e1sobi\u010d",
  "Zone": "Z\u00f3na", "Minutes": "Min\u00faty", "max {0}": "max {0}", "own days": "vlastn\u00e9 dni", "Run now": "Spusti\u0165 teraz",
  "Delete slot": "Zmaza\u0165 slot", "No slots yet.": "Zatia\u013e \u017eiadne sloty.", "+ Add slot": "+ Prida\u0165 slot",
  "Preview \u2013 next 7 days": "N\u00e1h\u013ead \u2013 najbli\u017e\u0161\u00edch 7 dn\u00ed", "(unsaved)": "(neulo\u017een\u00e9)", "Runs and conflicts": "Behy a konflikty",
  "(disabled)": "(vypnut\u00e1)", "use": "pou\u017ei\u0165", "ESP position {0}": "poz\u00edcia v ESP {0}", "ESP max {0}\u2032": "ESP max {0}\u2032",
  "max per run": "max na beh", "max per day": "max za de\u0148", "Run now (min)": "Spusti\u0165 (min)", "icon": "ikona",
  "Planner": "Pl\u00e1nova\u010d", "Planner enabled": "Pl\u00e1nova\u010d zapnut\u00fd", "Dry run (send nothing to the ESP)": "Sk\u00fa\u0161ka (do ESP ni\u010d neposiela\u0165)",
  "Language": "Jazyk", "automatic": "automaticky", "Merging slots": "Sp\u00e1janie slotov", "merge when closer than": "spoji\u0165, ak s\u00fa bli\u017e\u0161ie ako",
  "merge only when overlapping": "spoji\u0165 len pri prekryve", "never merge, shift the later run": "nesp\u00e1ja\u0165, posun\u00fa\u0165 neskor\u0161\u00ed",
  "same zone in both": "rovnak\u00e1 z\u00f3na v oboch", "longer": "dlh\u0161ia", "sum": "s\u00fa\u010det", "separate": "zvl\u00e1\u0161\u0165",
  "Timing uses valve overlap {0} s (integration options) and pump delay {1} s.": "\u010casovanie: prekryv ventilov {0} s (mo\u017enosti integr\u00e1cie), oneskorenie \u010derpadla {1} s.",
  "Pump": "\u010cerpadlo", "type to search\u2026": "p\u00ed\u0161 pre h\u013eadanie\u2026", "on before a run": "zapn\u00fa\u0165 pred behom", "then wait": "potom \u010daka\u0165",
  "off after": "vypn\u00fa\u0165 po", "warn if off": "upozorni\u0165, ak je vypnut\u00e9", "Notifications": "Upozornenia", "Send to": "Posla\u0165",
  "(default for every event, pick any number)": "(predvolen\u00e9 pre ka\u017ed\u00fa udalos\u0165, \u013eubovo\u013en\u00fd po\u010det)", "no notify services": "\u017eiadne notify slu\u017eby",
  "nobody": "nikomu", "default recipients": "predvolen\u00ed pr\u00edjemcovia", "Title": "Nadpis", "Message": "Spr\u00e1va",
  "own recipients for this event": "vlastn\u00ed pr\u00edjemcovia pre t\u00fato udalos\u0165", "minutes before": "min\u00fat vopred", "Buttons": "Tla\u010didl\u00e1",
  "Send test": "Posla\u0165 test", "Variables": "Premenn\u00e9", "Android: icon, HTML, max 3 buttons. iOS: plain text.": "Android: ikona, HTML, max 3 tla\u010didl\u00e1. iOS: \u010dist\u00fd text.",
  "Unsaved changes": "Neulo\u017een\u00e9 zmeny", "Revert": "Zahodi\u0165", "Save": "Ulo\u017ei\u0165", "Save the changes first.": "Najprv ulo\u017e zmeny.",
  "Dry run is OFF - this will really water. Start now?": "Sk\u00fa\u0161ka je VYPNUT\u00c1 - naozaj sa bude polieva\u0165. Spusti\u0165?",
  "Delete slot \"{0}\"?": "Zmaza\u0165 slot \"{0}\"?", "Weather": "Po\u010dasie", "Mode": "Re\u017eim", "off": "vypnut\u00e9",
  "suggest (Accept / Dismiss)": "navrhova\u0165 (Prija\u0165 / Zamietnu\u0165)", "automatic": "automaticky", "Forecast": "Predpove\u010f",
  "Rain sensor (fallen)": "Senzor zr\u00e1\u017eok (spadnut\u00e9)", "Temperature sensor": "Senzor teploty",
  "skip at": "presko\u010di\u0165 pri", "mm rain (fallen + expected)": "mm zr\u00e1\u017eok (spadnut\u00e9 + o\u010dak\u00e1van\u00e9)",
  "less rain reduces the minutes": "menej da\u017e\u010fa skr\u00e1ti min\u00faty", "count forecast": "po\u010d\u00edta\u0165 predpove\u010f", "h ahead": "h dopredu",
  "only hours with probability \u2265": "len hodiny s pravdepodobnos\u0165ou \u2265", "skip at wind \u2265": "presko\u010di\u0165 pri vetre \u2265",
  "skip below": "presko\u010di\u0165 pod", "\u00b0C (frost)": "\u00b0C (mr\u00e1z)", "100 % at a daily max of": "100 % pri dennom maxime",
  "\u00b0C, change per degree": "\u00b0C, zmena na stupe\u0148", "limits": "limity", "suggest for runs within": "navrhova\u0165 pre behy do",
  "Refresh": "Obnovi\u0165", "forecast {0} \u00b7 {1} hourly items": "predpove\u010f {0} \u00b7 {1} hodinov\u00fdch polo\u017eiek", "now {0} \u00b0C": "teraz {0} \u00b0C",
  "fallen {0} mm": "spadlo {0} mm", "Suggestions": "N\u00e1vrhy", "Accept": "Prija\u0165", "Dismiss": "Zamietnu\u0165",
  "skip": "presko\u010di\u0165", "adjust": "upravi\u0165", "run": "spusti\u0165", "{0} % of the minutes": "{0} % min\u00fat",
  "Skipped": "Presko\u010den\u00e9", "Undo": "Vr\u00e1ti\u0165", "Run anyway": "Spusti\u0165 aj tak", "skipped by you": "presko\u010dil si",
  "weather skip": "presko\u010den\u00e9 kv\u00f4li po\u010dasiu", "Meters (optional)": "Mera\u010de (volite\u013en\u00e9)", "Water flow": "Prietok vody",
  "Water meter (total)": "Vodomer (celkovo)", "Pump power": "Pr\u00edkon \u010derpadla", "Pump energy (total)": "Energia \u010derpadla (celkovo)",
  "warn when a zone's flow differs by": "upozorni\u0165, ak sa prietok z\u00f3ny l\u00ed\u0161i o", "% from usual": "% od be\u017en\u00e9ho",
  "Totals are preferred; without them the rate is integrated while a zone is open.": "Prednos\u0165 maj\u00fa celkov\u00e9 hodnoty; bez nich sa integruje okam\u017eit\u00e1 hodnota po\u010das otvorenej z\u00f3ny.",
  "This week": "Tento t\u00fd\u017ede\u0148", "This month": "Tento mesiac", "This year": "Tento rok", "All time": "Celkovo",
  "runs": "behov", "valve openings": "otvoren\u00ed", "skips": "presko\u010den\u00ed", "day": "de\u0148", "week": "t\u00fd\u017ede\u0148", "month": "mesiac", "year": "rok",
  "Watering time": "\u010cas polievania", "Water": "Voda", "Pump energy": "Energia \u010derpadla", "Per zone": "Pod\u013ea z\u00f3n",
  "avg flow": "priem. prietok", "usual": "be\u017en\u00fd", "avg power": "priem. pr\u00edkon", "saved by skips": "u\u0161etren\u00e9 presko\u010den\u00edm",
  "No statistics yet - they start with the first real run.": "Zatia\u013e \u017eiadne \u0161tatistiky - za\u010dn\u00fa prv\u00fdm skuto\u010dn\u00fdm behom.",
  "Pick zones and minutes, then run once.": "Vyber z\u00f3ny a min\u00faty a spusti jednorazovo.", "Run": "Spusti\u0165", "Cancel": "Zru\u0161i\u0165",
  "Pick at least one zone.": "Vyber aspo\u0148 jednu z\u00f3nu.", "Dry run is OFF - this will really water for {0} min. Start now?": "Sk\u00fa\u0161ka je VYPNUT\u00c1 - naozaj sa bude polieva\u0165 {0} min. Spusti\u0165?",
  "Event": "Udalos\u0165", "planned_ev": "napl\u00e1novan\u00e9", "started_ev": "spusten\u00e9", "zone_changed_ev": "zmena z\u00f3ny", "finished_ev": "skon\u010den\u00e9",
  "skipped_ev": "presko\u010den\u00e9", "stopped_ev": "zastaven\u00e9", "error_ev": "chyba", "pump_off_ev": "\u010derpadlo vypnut\u00e9", "dry_run_ev": "sk\u00fa\u0161ka",
  "suggestion_ev": "n\u00e1vrh po\u010dasia", "weather_ev": "zmena kv\u00f4li po\u010dasiu", "flow_warning_ev": "neobvykl\u00fd prietok",
  "Stop_a": "Zastavi\u0165", "Skip_a": "Presko\u010di\u0165", "Turn pump ON_a": "Zapn\u00fa\u0165 \u010derpadlo", "Accept_a": "Prija\u0165", "Dismiss_a": "Zamietnu\u0165",
  "no forecast in range": "mimo predpovede",
  "help_start": "Beh za\u010dne v tomto \u010dase.", "help_finish": "Beh sa napl\u00e1nuje dozadu tak, aby skon\u010dil v tomto \u010dase.",
  "help_offset_sun": "Posun: -30 = 30 min pred, +60 = 1 h po v\u00fdchode/z\u00e1pade slnka (men\u00ed sa ka\u017ed\u00fd de\u0148).",
  "help_offset_time": "Posun posunie \u010das o min\u00faty (pri pevnom \u010dase zvy\u010dajne 0).",
  "help_reverse": "Opa\u010dne: z\u00f3ny id\u00fa od posledn\u00e9ho ventilu v ESP po prv\u00fd.",
  "help_weather": "Upravi\u0165 pod\u013ea po\u010dasia: po\u010dasie m\u00f4\u017ee slot skr\u00e1ti\u0165, pred\u013a\u017ei\u0165 alebo presko\u010di\u0165; vypnut\u00e9 = v\u017edy presn\u00e9 min\u00faty.", "follow weather": "riadi\u0165 sa po\u010das\u00edm", "ignores weather": "ignoruje po\u010dasie",
  "Off for a greenhouse or indoor zone: the weather never shortens, lengthens or skips it.": "Vypni pre sklen\u00edk alebo vn\u00fatorn\u00fa z\u00f3nu: po\u010dasie ju nikdy neskr\u00e1ti, nepred\u013a\u017ei ani nepresko\u010d\u00ed.",
  "Skip when rain reaches": "Presko\u010di\u0165, ke\u010f zr\u00e1\u017eky dosiahnu", "change per degree": "zmena na stupe\u0148", "at least": "najmenej",
  "at most": "najviac", "Zones with follow weather off are never changed.": "Z\u00f3ny s vypnut\u00fdm riaden\u00edm po\u010das\u00edm sa nemenia.",
};
const EN = {
  "help_start": "The run starts at this time.", "help_finish": "The run is planned backwards so that it ends at this time.",
  "help_offset_sun": "Offset moves it: -30 = 30 min before, +60 = 1 h after sunrise/sunset (which changes every day).",
  "help_offset_time": "Offset shifts the time by minutes (usually 0 for a fixed time).",
  "help_reverse": "Reverse: zones run from the last ESP valve to the first.",
  "help_weather": "Adjust by weather: the weather can shorten, lengthen or skip this slot; off = always the exact minutes.",
};
const DAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAYS_SK = ["Po", "Ut", "St", "\u0160t", "Pi", "So", "Ne"];
const MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MON_SK = ["jan", "feb", "mar", "apr", "m\u00e1j", "j\u00fan", "j\u00fal", "aug", "sep", "okt", "nov", "dec"];
let LANG = "en";
const t = (s, ...a) => {
  let x = (LANG === "sk" && SK[s]) || EN[s] || (/_ev$/.test(s) ? s.slice(0, -3).replace(/_/g, " ") : s.replace(/_a$/, ""));
  a.forEach((v, i) => { x = x.split(`{${i}}`).join(v); });
  return x;
};
const DAYS = () => (LANG === "sk" ? DAYS_SK : DAYS_EN);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hm = (iso) => (iso ? iso.slice(11, 16) : "\u2013");
const dayOf = (iso) => (iso ? iso.slice(0, 10) : "");
const minOfDay = (iso) => +iso.slice(11, 13) * 60 + +iso.slice(14, 16) + (+iso.slice(17, 19) || 0) / 60;
const clone = (o) => JSON.parse(JSON.stringify(o ?? null));
const wd = (d) => (new Date(d + "T12:00:00").getDay() + 6) % 7;
const fmtDay = (d) => { const x = new Date(d + "T12:00:00"); return `${DAYS()[wd(d)]} ${x.getDate()}.${x.getMonth() + 1}.`; };
const addDays = (d, n) => { const x = new Date(d + "T12:00:00"); x.setDate(x.getDate() + n); return x.toISOString().slice(0, 10); };
const runKey = (r) => `${r.day}|${r.slots.join("+")}`;
const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));
const r1 = (v) => (v === null || v === undefined ? "\u2013" : Math.round(v * 10) / 10);
const fmtMin = (m) => { m = Math.round(m || 0); return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")} h` : `${m} min`; };
const hmm = (m) => { m = Math.round(m || 0); return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}` : `${m}\u2032`; };
const fmtL = (l) => (l === null || l === undefined ? "\u2013" : l >= 1000 ? `${(l / 1000).toFixed(2)} m\u00b3` : `${Math.round(l)} L`);
const fmtKwh = (k) => (k === null || k === undefined ? "\u2013" : k < 1 ? `${Math.round(k * 1000)} Wh` : `${k.toFixed(2)} kWh`);

class EspSprinklerPlannerCard extends HTMLElement {
  setConfig(config) {
    this._cfg = config || {};
    this._tab = this._cfg.tab || "today";
    this._open = new Set();
    this._qr = null;            // quick run dialog state
    this._sp = { period: "week", count: 12, metric: "min" };
    this._dets = {};            // open state of <details data-d=...>, kept across renders
    if (this._tab === "zones") this._tab = "settings";
  }

  static getStubConfig() { return {}; }
  getCardSize() { return 9; }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._init();
    else this._watch();
  }

  // ------------------------------------------------------------------ data
  _init() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${CSS}</style><ha-card><div class="wrap"><div class="muted pad">Loading\u2026</div></div></ha-card>`;
    this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.addEventListener("input", (e) => this._onInput(e, false));
    this.shadowRoot.addEventListener("change", (e) => this._onInput(e, true));
    this.shadowRoot.addEventListener("toggle", (e) => { const k = e.target.dataset && e.target.dataset.d; if (k) this._dets[k] = e.target.open; }, true);
    this._load();
    this._timer = setInterval(() => this._load(), 60000);
    this._tick = setInterval(() => this._moveNow(), 10000);
  }

  disconnectedCallback() { clearInterval(this._timer); clearInterval(this._tick); this._timer = null; }
  connectedCallback() { if (this._hass && !this._timer) { this._timer = setInterval(() => this._load(), 60000); } }

  _watch() {
    const e = (this.data && this.data.entities) || {};
    const ids = [e.status, e.next_run, e.active_zone].filter(Boolean);
    const sig = ids.map((id) => (this._hass.states[id] || {}).last_updated).join("|");
    if (this._sig !== undefined && sig !== this._sig) { clearTimeout(this._wt); this._wt = setTimeout(() => this._load(), 400); }
    this._sig = sig;
  }

  async _ws(msg) {
    const m = { ...msg };
    if (this._cfg.entry_id) m.entry_id = this._cfg.entry_id;
    return this._hass.callWS(m);
  }

  async _load() {
    try {
      const d = await this._ws({ type: `${DOMAIN}/get`, days: 7 });
      this.data = d;
      this._fetched = Date.now();
      this._loadErr = null;
      if (!this.dirty) { this.draft = this._makeDraft(d); this.preview = null; }
      if (this._tab === "stats") this._loadStats(false);
    } catch (err) {
      this._loadErr = err.message || String(err);
    }
    this._render();
  }

  async _loadStats(render = true) {
    try {
      this._stats = await this._ws({ type: `${DOMAIN}/stats`, period: this._sp.period, count: this._sp.count });
    } catch (err) { this._stats = { error: err.message || String(err) }; }
    if (render) this._render();
  }

  _makeDraft(d) {
    const c = d.config || {};
    return {
      zones: clone(c.zones || {}), slots: clone(c.slots || []), settings: clone(c.settings || {}),
      pump: clone(c.pump || {}), notifications: clone(c.notifications || { targets: [], events: {} }),
      weather: clone(c.weather || {}), meters: clone(c.meters || {}), ui: clone(c.ui || {}),
    };
  }

  _markDirty(structural) {
    this.dirty = true;
    this._saveErr = null;
    if (structural) this._render(); else this._renderBar();
    clearTimeout(this._pt);
    this._pt = setTimeout(() => this._runPreview(), 400);
  }

  async _runPreview() {
    try {
      this.preview = await this._ws({ type: `${DOMAIN}/preview`, days: 7, config: this.draft });
    } catch (err) {
      this.preview = { error: err.message || String(err), runs: [], conflicts: [] };
    }
    this._renderPreview();
  }

  // ------------------------------------------------------------------ helpers
  _lang() {
    const want = (this.draft && this.draft.ui && this.draft.ui.language) || "auto";
    if (want === "en" || want === "sk") return want;
    return (this.data && this.data.lang) || ((this._hass.locale || {}).language || this._hass.language || "en").slice(0, 2);
  }

  _zones() {
    const zc = (this.draft && this.draft.zones) || {};
    return (this.data.valves || []).slice().sort((a, b) => a.order - b.order).map((v, i) => ({
      ...v, name: (zc[v.id] && zc[v.id].name) || v.name || v.id,
      enabled: zc[v.id] && zc[v.id].enabled !== undefined ? zc[v.id].enabled : v.enabled !== false,
      color: (zc[v.id] && zc[v.id].color) || PALETTE[i % PALETTE.length],
      icon: (zc[v.id] && zc[v.id].icon) || "",
    }));
  }

  _zone(zid) { return this._zones().find((x) => x.id === zid); }
  _color(zid) { const z = this._zone(zid); return z ? z.color : "#888"; }
  _mark(z, big) {
    if (z && z.icon) return `<ha-icon class="zi ${big ? "big" : ""}" icon="${esc(z.icon)}" style="color:${z.color}"></ha-icon>`;
    return `<span class="dot" style="background:${z ? z.color : "#888"}"></span>`;
  }
  _plan() { return this.dirty && this.preview && !this.preview.error ? this.preview : this.data.plan; }
  _nowIso() {
    const elapsed = (Date.now() - (this._fetched || Date.now())) / 60000;
    const base = this.data.now; const m = minOfDay(base) + elapsed;
    return { day: dayOf(base), min: m };
  }
  _sun(day) { return (this.data.sun || []).find((s) => s.day === day) || {}; }
  _blocked(plan) { return new Set([...(plan.skipped || []), ...(plan.weather_skipped || [])]); }
  _nextRun(plan) {
    const now = this.data.now; const b = this._blocked(plan);
    return (plan.runs || []).find((r) => r.start > now && !b.has(runKey(r)));
  }
  _slotName(id) { const s = (this.draft.slots || []).find((x) => x.id === id); return (s && s.name) || (id === "quick" ? t("Quick run") : id); }
  _fname(e) { return ((this._hass.states[e] || {}).attributes || {}).friendly_name || e; }
  _picker(path, value, filter, listId, placeholder) {
    if (value && this._editing !== path) {
      const st = this._hass.states[value];
      const val = st ? `${st.state}${(st.attributes || {}).unit_of_measurement ? " " + st.attributes.unit_of_measurement : ""}` : t("missing");
      return `<span class="echip ${st ? "" : "bad"}"><button class="en" data-act="editpick" data-path="${path}" title="${esc(value)}">
          <ha-icon icon="${esc((st && st.attributes.icon) || "mdi:link-variant")}"></ha-icon><span class="enm">${esc(this._fname(value))}</span><span class="eid">${esc(value)}</span></button>
          <span class="ev">${esc(val)}</span><button class="xr" data-act="clearpick" data-path="${path}" title="${esc(t("Remove"))}"><ha-icon icon="mdi:close"></ha-icon></button></span>`;
    }
    const cands = Object.keys(this._hass.states).filter(filter).sort();
    return `<input class="picker" list="${listId}" data-pick="${path}" value="${esc(value || "")}" placeholder="${esc(placeholder || t("type to search\u2026"))}">
      <datalist id="${listId}">${cands.map((e) => `<option value="${esc(e)}">${esc(this._fname(e))}</option>`).join("")}</datalist>`;
  }
  _unitOf(e) { return (((this._hass.states[e] || {}).attributes || {}).unit_of_measurement || ""); }
  _decision(r, plan) { return ((plan.weather || {})[runKey(r)]) || null; }
  _open_(key, dflt) { return (this._dets[key] ?? dflt) ? "open" : ""; }
  _det(key, dflt, summary, body, cls) {
    return `<details class="${cls || "sec"}" data-d="${key}" ${this._open_(key, dflt)}><summary>${summary}</summary><div class="secb">${body}</div></details>`;
  }
  _slider(path, value, min, max, step, unit) {
    const v = value ?? min;
    return `<span class="sl"><input type="range" data-k="${path}" data-t="num" data-u="${esc(unit || "")}" min="${min}" max="${max}" step="${step}" value="${esc(v)}"><output>${esc(v)}${esc(unit || "")}</output></span>`;
  }
  _cur() { return ((this.data && this.data.weather_now) || {}).currency || "EUR"; }
  _cost(x) {
    const m = (this.data && this.data.meters) || {};
    if (!x || (!m.water_price && !m.energy_price)) return null;
    const c = (x.l ? x.l / 1000 * (m.water_price || 0) : 0) + (x.kwh ? x.kwh * (m.energy_price || 0) : 0);
    if (!c) return null;
    try { return new Intl.NumberFormat(LANG === "sk" ? "sk-SK" : "en-GB", { style: "currency", currency: this._cur() }).format(c); } catch (e) { return c.toFixed(2) + " " + this._cur(); }
  }
  _title() { return this._cfg.title || ((this.draft && this.draft.ui) || {}).title || this.data.title; }

  // ------------------------------------------------------------------ rendering
  _render() {
    const root = this.shadowRoot.querySelector(".wrap");
    if (!root) return;
    if (!this.data) { root.innerHTML = `<div class="pad err">${esc(this._loadErr || t("Loading\u2026"))}</div>`; return; }
    LANG = this._lang();
    const d = this.data;
    const flags = d.flags || {};
    const STATUS = { idle: "Idle", scheduled: "Scheduled", running: "Running", dry_run: "Dry run", disabled: "Disabled", error: "Error" };
    const tabs = [["today", "Overview"], ["week", "Week"], ["stats", "Stats"], ["slots", "Slots"], ["settings", "Settings"]];
    root.innerHTML = `
      <div class="head">
        <ha-icon class="hicon ${flags.enabled ? "" : "off"}" icon="mdi:sprinkler-variant"></ha-icon>
        <div class="title">${esc(this._title())}</div>
        <span class="chip st-${esc(d.status)}">${esc(t(STATUS[d.status] || d.status))}</span>
        ${flags.dry_run ? `<span class="chip warn" title="${esc(t("Nothing is sent to the ESP"))}">${t("DRY RUN")}</span>` : ""}
        <label class="master" title="${esc(t("Planner enabled"))}"><input type="checkbox" class="tog" data-flag="enabled" ${flags.enabled ? "checked" : ""}></label>
      </div>
      ${d.error ? `<div class="banner err">${esc(d.error)}</div>` : ""}
      ${this._loadErr ? `<div class="banner err">${esc(this._loadErr)}</div>` : ""}
      <div class="tabs">${tabs.map(([k, l]) => `<button class="tab ${this._tab === k ? "on" : ""}" data-tab="${k}">${t(l)}</button>`).join("")}</div>
      <div class="body">${this[`_tab_${this._tab}`]()}</div>
      <div class="bar"></div>`;
    this._renderBar();
    this._renderPreview();
  }

  _renderBar() {
    const bar = this.shadowRoot.querySelector(".bar");
    if (!bar) return;
    bar.innerHTML = this.dirty ? `
      <span class="grow">${this._saveErr ? `<span class="err">${esc(this._saveErr)}</span>` : t("Unsaved changes")}</span>
      <button data-act="revert">${t("Revert")}</button><button class="primary" data-act="save">${t("Save")}</button>` : "";
    bar.classList.toggle("show", !!this.dirty);
  }

  _renderPreview() {
    for (const el of this.shadowRoot.querySelectorAll("[data-preview]")) {
      const kind = el.dataset.preview;
      el.innerHTML = kind === "runs" ? this._runsList(this._plan()) : this._weekRows(this._plan(), true);
    }
  }

  // --- timeline
  _timeline(day, plan, compact) {
    const sun = this._sun(day);
    const now = this._nowIso();
    const bars = [];
    const userSkip = new Set(plan.skipped || []); const wxSkip = new Set(plan.weather_skipped || []);
    for (const r of plan.runs || []) {
      const sd = dayOf(r.start), ed = dayOf(r.end);
      if (sd !== day && ed !== day) continue;
      const s = sd === day ? minOfDay(r.start) : 0;
      const e = ed === day ? minOfDay(r.end) : 1440;
      if (e <= s) continue;
      const segs = r.zones.map((z) => `<i style="flex:${z.minutes};background:${this._color(z.zone)}" title="${esc(z.name)} ${z.minutes} min"></i>`).join("");
      const k = runKey(r);
      const dec = this._decision(r, plan);
      const tip = `${hm(r.start)}\u2013${hm(r.end)} ${r.slots.map((x) => this._slotName(x)).join(" + ")}\n` + r.zones.map((z) => `${z.name}: ${z.minutes} min`).join("\n")
        + (r.notes.length ? "\n" + r.notes.join("\n") : "") + (dec && dec.reasons.length ? `\n${t("Weather")}: ${dec.reasons.join(", ")}` : "");
      bars.push(`<div class="run ${r.merged ? "merged" : ""} ${userSkip.has(k) ? "skipped" : ""} ${wxSkip.has(k) ? "skipped wx" : ""}" style="left:${(s / 14.4).toFixed(3)}%;width:${Math.max(0.4, (e - s) / 14.4).toFixed(3)}%" title="${esc(tip)}">${segs}</div>`);
    }
    const mark = (iso, cls, label) => (iso && dayOf(iso) === day ? `<div class="mark ${cls}" style="left:${(minOfDay(iso) / 14.4).toFixed(3)}%" title="${label} ${hm(iso)}"></div>` : "");
    const ticks = [0, 3, 6, 9, 12, 15, 18, 21].map((h) => `<span style="left:${(h * 60 / 14.4).toFixed(2)}%">${h}</span>`).join("");
    return `<div class="tl ${compact ? "compact" : ""}">
      ${mark(sun.sunrise, "sunrise", t("Sunrise"))}${mark(sun.sunset, "sunset", t("Sunset"))}
      ${now.day === day ? `<div class="mark now" style="left:${(now.min / 14.4).toFixed(3)}%"></div>` : ""}
      ${bars.join("")}
      ${compact ? "" : `<div class="ticks">${ticks}</div>`}
    </div>`;
  }

  _wxDay(day) { return ((this.data.weather_now || {}).days || []).find((x) => x.day === day); }
  _runMark(r, plan) {
    const k = runKey(r);
    if ((plan.skipped || []).includes(k)) {
      if (r.start <= this.data.now) return `<span class="rm user" title="${esc(t("skipped by you"))}">\u2715</span>`;
      return `<span class="rm user ans" data-act="unskip" data-key="${esc(k)}" title="${esc(t("Skipped by you. Click to undo."))}">\u2715</span>`;
    }
    const dec = this._decision(r, plan);
    const tip = `${hm(r.start)} ${r.slots.map((x) => this._slotName(x)).join(" + ")}${dec && dec.reasons.length ? ": " + dec.reasons.join(", ") : ""}`;
    if (dec && dec.status === "dismissed")
      return `<span class="rm ok ans" data-act="sugreset" data-key="${esc(k)}" title="${esc(t("Dismissed: runs as planned. Click to take back."))}\n${esc(tip)}">\u2713</span>`;
    if (!dec || dec.status === "none" || dec.action === "run") {
      const wxOn = ((this.data.weather_full || {}).mode || "off") !== "off";
      return `<span class="rm ok" title="${esc(tip)}">${wxOn && !dec ? "\u00b7" : "\u2713"}</span>`;
    }
    const pct = Math.round((dec.factor - 1) * 100);
    const what = dec.action === "skip" ? "\u2715" : `${pct > 0 ? "+" : "\u2212"}${Math.abs(pct)}%`;
    if (dec.status === "pending")      // only a suggestion: nothing changes until you accept it
      return `<span class="rm sug ${dec.action}" data-act="sugyes" data-key="${esc(k)}" title="${esc(t("Suggestion (not applied): {0}", tip))}\n${esc(t("Click to accept"))}"><ha-icon icon="mdi:lightbulb-on-outline"></ha-icon>${what}</span>`;
    if (dec.status === "accepted")
      return `<span class="rm ${dec.action === "skip" ? "skip" : "adj"} ans" data-act="sugreset" data-key="${esc(k)}" title="${esc(t("Accepted. Click to take back."))}\n${esc(tip)}">${what}</span>`;
    return `<span class="rm ${dec.action === "skip" ? "skip" : "adj"}" title="${esc(tip)}">${what}</span>`;
  }

  _wxBadge(day, plan) {
    const w = this._wxDay(day);
    const runs = (plan.runs || []).filter((r) => r.day === day);
    return `<span class="wxi">${w && w.cond ? `<ha-icon icon="mdi:weather-${WX_ICON[w.cond] || "cloudy"}"></ha-icon>` : ""}</span>
      <span class="wxt">${w && w.tmax !== null && w.tmax !== undefined ? `${Math.round(w.tmax)}\u00b0` : ""}</span>
      <span class="wxr rain">${w && w.rain ? `${r1(w.rain)} mm` : ""}</span>
      <span class="wxm">${runs.map((r) => this._runMark(r, plan)).join("")}</span>`;
  }

  _weekRows(plan, small) {
    if (plan.error) return `<div class="err">${esc(plan.error)}</div>`;
    const start = dayOf(this.data.now);
    let out = "";
    for (let i = 0; i < 7; i++) {
      const day = addDays(start, i);
      out += `<div class="wrow"><div class="wday">${fmtDay(day)}</div><div class="wtl">${this._timeline(day, plan, true)}</div><div class="wwx">${this._wxBadge(day, plan)}</div></div>`;
    }
    void small;
    return out + this._legend();
  }

  _legend(extra) {
    return `<div class="legend">${this._zones().map((z) => `<span>${z.icon ? this._mark(z) : `<i style="background:${z.color}"></i>`}${esc(z.name)}</span>`).join("")}${extra || ""}</div>`;
  }

  _runsList(plan) {
    if (plan.error) return `<div class="banner err">${esc(plan.error)}</div>`;
    const conf = (plan.conflicts || []).map((c) => `<li class="err">${esc(c.day)}: ${esc(c.message)}</li>`).join("");
    const rows = (plan.runs || []).slice(0, 30).map((r) => {
      const dec = this._decision(r, plan);
      return `<li class="${r.end < this.data.now ? "past" : ""}">
        <b>${fmtDay(r.day)} ${hm(r.start)}\u2013${hm(r.end)}</b> ${r.slots.map((x) => esc(this._slotName(x))).join(" + ")}
        ${r.merged ? `<span class="chip small">${t("merged")}</span>` : ""}${r.reverse ? `<span class="chip small">${t("reverse")}</span>` : ""}
        <div class="muted">${r.zones.map((z) => `${this._mark(this._zone(z.zone))}${esc(z.name)} ${z.minutes}\u2032`).join("  ")}</div>
        ${r.notes.length ? `<div class="note">${r.notes.map(esc).join("<br>")}</div>` : ""}
        ${dec && dec.reasons.length ? `<div class="note wxn">${t("Weather")}: ${esc(dec.reasons.join(", "))}${dec.status === "pending" ? ` (${t("Suggestions").toLowerCase()})` : ""}</div>` : ""}</li>`;
    }).join("");
    return `${conf ? `<ul class="list">${conf}</ul>` : ""}<ul class="list">${rows || `<li class="muted">${t("No runs in the next 7 days.")}</li>`}</ul>`;
  }

  // --- tabs
  _tab_today() {
    const d = this.data; const plan = d.plan; const next = this._nextRun(plan);
    const az = d.active_zone; const act = d.active;
    const zones = this._zones();
    const today = dayOf(d.now);
    const todayHist = (d.history || {})[today] || {};
    const slots = this.draft.slots || [];
    const blocked = this._blocked(plan);
    return `
      <div class="grid2">
        <div class="box">
          <div class="lbl">${t("Now")}</div>
          ${act ? `<div class="big">${az ? `${this._mark(this._zone(az.zone), true)}${esc(az.name)}` : act.dry_run ? t("Dry run") : t("Starting\u2026")}</div>
                   <div class="muted">${az && az.until ? `${t("until {0}", hm(az.until))} \u00b7 ` : ""}${t("run ends {0}", hm(act.run.end))}</div>
                   ${this._progress(act)}
                   <button class="ab danger stopnow" data-act="stop" title="${esc(t("Stop"))}"><ha-icon icon="mdi:stop-circle"></ha-icon>${t("Stop")}</button>`
                : `<div class="big muted">${t("Nothing running")}</div>`}
        </div>
        <div class="box ${(d.flags || {}).enabled ? "" : "boxoff"}">
          <div class="lbl">${t("Next run")}${(d.flags || {}).enabled ? "" : ` <span class="chip offc">${t("Planner off")}</span>`}</div>
          ${next ? `<div class="big ${(d.flags || {}).enabled ? "" : "struck"}">${fmtDay(next.day)} ${hm(next.start)} ${this._runMark(next, plan)}</div><div class="muted">${next.slots.map((x) => esc(this._slotName(x))).join(" + ")} \u00b7 ${t("until {0}", hm(next.end))}</div>
                    ${this._zoneStrip(next.zones)}`
                 : `<div class="big muted">\u2013</div>`}
        </div>
      </div>
      ${this._actionBar(act, next, slots)}
      ${this._qr ? this._quickRun() : ""}
      ${this._suggestBox(plan)}
      ${this._skippedBox(plan)}
      ${this._liveRow()}
      ${this._forecastStrip(plan)}
      ${this._dayPanel(plan)}
      <div class="lbl">${t("Today")}</div>
      ${this._timeline(today, plan, false)}
      <div class="lbl lrow">${t("Zones today")}<span class="grow"></span>
        <button class="vt ${this._zview() === "list" ? "on" : ""}" data-act="zview" data-v="list" title="${t("list")}"><ha-icon icon="mdi:view-list"></ha-icon></button>
        <button class="vt ${this._zview() === "tiles" ? "on" : ""}" data-act="zview" data-v="tiles" title="${t("tiles")}"><ha-icon icon="mdi:view-grid"></ha-icon></button></div>
      ${this._zonesToday(zones, plan, todayHist, today, blocked, az)}`;
  }

  _zoneStrip(zs) {
    const total = zs.reduce((a, z) => a + z.minutes, 0) || 1;
    const MAX = 6;
    const shown = zs.slice(0, MAX);
    const more = zs.slice(MAX);
    return `<div class="zbar" title="${esc(zs.map((z) => `${z.name}: ${z.minutes}\u2032`).join("\n"))}">${zs.map((z) => `<i style="flex:${z.minutes};background:${this._color(z.zone)}"></i>`).join("")}</div>
      <div class="nz">${shown.map((z) => `<span title="${esc(z.name)} ${z.minutes}\u2032">${this._mark(this._zone(z.zone))}${z.minutes}\u2032</span>`).join("")}
      ${more.length ? `<span class="chip small more" title="${esc(more.map((z) => `${z.name}: ${z.minutes}\u2032`).join("\n"))}">+${more.length}</span>` : ""}
      <span class="muted nzt">${t("{0} zones", zs.length)} \u00b7 ${fmtMin(total)}</span></div>`;
  }

  _zview() { return this._zv || localStorage.getItem("esp_sprinkler_zview") || this._cfg.zones || "list"; }

  _zonesToday(zones, plan, todayHist, today, blocked, az) {
    const d = this.data;
    const info = zones.map((z) => {
      const nx = (plan.runs || []).find((r) => r.start > d.now && !blocked.has(runKey(r)) && r.zones.some((x) => x.zone === z.id));
      const zm = nx && nx.zones.find((x) => x.zone === z.id);
      const done = todayHist[z.id] || 0;
      const left = (plan.runs || []).filter((r) => r.day === today && r.start > d.now && !blocked.has(runKey(r))).reduce((a, r) => a + ((r.zones.find((x) => x.zone === z.id) || {}).minutes || 0), 0);
      return { z, nx, zm, done, left, on: az && az.zone === z.id };
    });
    const maxT = Math.max(1, ...info.map((x) => x.done + x.left));
    const nextTxt = (x) => (x.nx ? `${x.nx.day === today ? "" : DAYS()[wd(x.nx.day)] + " "}${hm(x.nx.start)} \u00b7 ${x.zm.minutes}\u2032` : "\u2013");
    if (this._zview() === "tiles") {
      return `<div class="tiles">${info.map((x) => { const tot = Math.max(x.done + x.left, 1);
        return `<div class="tile ${x.z.enabled ? "" : "dis"} ${x.on ? "on" : ""}">
          <div class="tn">${this._mark(x.z, true)}${esc(x.z.name)}${x.on ? ` <span class="chip small run-on">ON</span>` : ""}</div>
          <div class="pbar"><i style="width:${(x.done / tot * 100).toFixed(1)}%;background:${x.z.color}"></i><i class="plan" style="width:${(x.left / tot * 100).toFixed(1)}%;--c:${x.z.color}"></i></div>
          <div class="tm"><b>${Math.round(x.done)}</b>${x.left ? `<span class="muted"> +${Math.round(x.left)}</span>` : ""} min<span class="grow"></span><span class="muted">\u23f5 ${nextTxt(x)}</span></div></div>`; }).join("")}</div>`;
    }
    return `<div class="zlist">${info.map((x) => `<div class="zr ${x.z.enabled ? "" : "dis"} ${x.on ? "on" : ""}" title="${esc(x.z.name)}: ${esc(t("{0} min watered today, {1} min still planned today", Math.round(x.done), Math.round(x.left)))}">
        <span class="zn">${this._mark(x.z)}${esc(x.z.name)}${x.on ? ` <span class="chip small run-on">ON</span>` : ""}</span>
        <span class="pbar thin"><i style="width:${(x.done / maxT * 100).toFixed(1)}%;background:${x.z.color}"></i><i class="plan" style="width:${(x.left / maxT * 100).toFixed(1)}%;--c:${x.z.color}"></i></span>
        <span class="zm"><b>${Math.round(x.done)}</b>${x.left ? `<span class="muted">+${Math.round(x.left)}</span>` : ""}\u2032</span>
        <span class="muted zx">\u23f5 ${nextTxt(x)}</span></div>`).join("")}</div>`;
  }

  _actionBar(act, next, slots) {
    return `<div class="abar">
      <button class="ab ${this._qr ? "on" : ""}" data-act="qr"><ha-icon icon="mdi:play-speed"></ha-icon>${t("Quick run")}</button>
      ${next ? `<button class="ab" data-act="skip" title="${esc(t("Skip next"))}: ${fmtDay(next.day)} ${hm(next.start)}"><ha-icon icon="mdi:skip-next-circle-outline"></ha-icon>${t("Skip")} <span class="muted">${DAYS()[wd(next.day)]} ${hm(next.start)}</span></button>` : ""}
      ${slots.length ? `<span class="ag" title="${esc(t("Run slot now"))}"><ha-icon icon="mdi:calendar-clock"></ha-icon><span class="agl">${t("Run slot")}</span>
        <select id="runslot">${slots.map((s) => `<option value="${esc(s.id)}">${esc(s.name || s.id)}</option>`).join("")}</select>
        <button class="ab primary" data-act="runslot" title="${esc(t("Run slot now"))}"><ha-icon icon="mdi:play"></ha-icon></button></span>` : ""}
    </div>`;
  }

  _progress(act) {
    const r = act.run; const s = Date.parse(r.start), e = Date.parse(r.end);
    const now = Date.now();
    const f = Math.max(0, Math.min(1, (now - s) / Math.max(1, e - s)));
    const left = Math.max(0, Math.round((e - now) / 60000));
    return `<div class="prog" data-s="${s}" data-e="${e}"><div class="psegs">${r.zones.map((z) => `<i style="flex:${z.minutes};background:${this._color(z.zone)}"></i>`).join("")}</div>
      <div class="pfill" style="left:${(f * 100).toFixed(2)}%"></div></div>
      <div class="muted small"><span class="pleft">${fmtMin(left)}</span> ${t("left")}</div>`;
  }

  _liveRow() {
    const c = (this.data.weather_now || {}).current || {};
    const items = [];
    if (c.temp !== undefined) items.push(["mdi:thermometer", `${r1(c.temp)} \u00b0C`, t("Temperature sensor")]);
    if (c.humidity !== undefined) items.push(["mdi:water-percent", `${Math.round(c.humidity)} %`, t("humidity")]);
    if (c.wind !== undefined) items.push(["mdi:weather-windy", `${Math.round(c.wind)} km/h`, t("wind")]);
    if (c.gust !== undefined) items.push(["mdi:weather-windy-variant", `${Math.round(c.gust)} km/h`, t("gusts")]);
    if (c.rain !== undefined) items.push(["mdi:weather-rainy", `${r1(c.rain)} mm`, t("Rain sensor (fallen)")]);
    if (c.raining !== undefined) items.push([c.raining ? "mdi:weather-pouring" : "mdi:weather-sunny", c.raining ? (c.rain_rate ? `${r1(c.rain_rate)} mm/h` : t("raining")) : t("dry"), t("Raining now (binary or mm/h)")]);
    if (!items.length) return "";
    return `<div class="live">${items.map(([i, v, l]) => `<span class="lc" title="${esc(l)}"><ha-icon icon="${i}"></ha-icon>${esc(v)}</span>`).join("")}</div>`;
  }

  _quickRun() {
    const zones = this._zones().filter((z) => z.enabled);
    const q = this._qr;
    return `<div class="box qr">
      <div class="lbl">${t("Quick run")}</div>
      <div class="muted small">${t("Pick zones and minutes, then run once.")}</div>
      <div class="qgrid">${zones.map((z) => `<label class="qz ${q.sel[z.id] ? "on" : ""}"><input type="checkbox" data-qz="${esc(z.id)}" ${q.sel[z.id] ? "checked" : ""}>${this._mark(z)}${esc(z.name)}
        <input type="number" class="n" min="0.5" step="0.5" data-qm="${esc(z.id)}" value="${esc(q.min[z.id] ?? 5)}"> min</label>`).join("")}</div>
      <div class="row"><label><input type="checkbox" data-qrev ${q.reverse ? "checked" : ""}> ${t("reverse ESP order")}</label>
        <span class="grow"></span><span class="muted">${fmtMin(zones.filter((z) => q.sel[z.id]).reduce((a, z) => a + (+q.min[z.id] || 5), 0))}</span>
        <button data-act="qrcancel">${t("Cancel")}</button><button class="primary" data-act="qrrun">${t("Run")}</button></div>
    </div>`;
  }

  _suggestBox(plan) {
    const sug = plan.suggestions || {};
    const keys = Object.keys(sug).sort();
    if (!keys.length) return "";
    return `<div class="box sug"><div class="lbl">${t("Weather")} \u2013 ${t("Suggestions")}</div>${keys.map((k) => {
      const s = sug[k]; const r = (plan.runs || []).find((x) => runKey(x) === k);
      const label = r ? `${fmtDay(r.day)} ${hm(r.start)} ${r.slots.map((x) => esc(this._slotName(x))).join(" + ")}` : esc(k);
      const what = s.action === "skip" ? t("skip") : `${t("adjust")} \u2192 ${t("{0} % of the minutes", Math.round(s.factor * 100))}`;
      return `<div class="row"><b>${label}</b><span>${esc(what)}</span><span class="muted">${esc((s.reasons || []).join(", "))}</span><span class="grow"></span>
        <button data-act="sugno" data-key="${esc(k)}">${t("Dismiss")}</button><button class="primary" data-act="sugyes" data-key="${esc(k)}">${t("Accept")}</button></div>`;
    }).join("")}</div>`;
  }

  _skippedBox(plan) {
    const now = this.data.now;
    const user = new Set(plan.skipped || []); const wx = new Set(plan.weather_skipped || []);
    const runs = (plan.runs || []).filter((r) => r.start > now && (user.has(runKey(r)) || wx.has(runKey(r)))).slice(0, 6);
    const answers = Object.values(plan.weather || {}).filter((v) => v.status === "accepted" || v.status === "dismissed").length;
    if (!runs.length && !answers) return "";
    return `<details class="box skp" data-d="skipped" ${this._open_("skipped", false)}><summary class="lbl lrow">${t("Skipped")} <span class="muted">${runs.map((r) => `${DAYS()[wd(r.day)]} ${hm(r.start)}`).join(", ")}</span><span class="grow"></span><button class="ab clr" data-act="clearall"><ha-icon icon="mdi:broom"></ha-icon>${t("Clear all")}</button></summary>${runs.map((r) => {
      const k = runKey(r); const isWx = wx.has(k) && !user.has(k); const dec = this._decision(r, plan);
      return `<div class="row"><b>${fmtDay(r.day)} ${hm(r.start)}</b> ${r.slots.map((x) => esc(this._slotName(x))).join(" + ")}
        <span class="muted">${isWx ? `${t("weather skip")}${dec ? ": " + esc(dec.reasons.join(", ")) : ""}` : t("skipped by you")}</span><span class="grow"></span>
        <button data-act="unskip" data-key="${esc(k)}">${isWx ? t("Run anyway") : t("Undo")}</button></div>`;
    }).join("")}</details>`;
  }

  _forecastStrip(plan) {
    const w = this.data.weather_now || {}; const full = this.data.weather_full || {};
    if (!full.mode || full.mode === "off") return "";
    const today = dayOf(this.data.now);
    const days = (w.days || []).filter((x) => x.day >= today).slice(0, 7);
    return `<div class="lbl">${t("Weather")} <span class="muted">${w.temp !== null && w.temp !== undefined ? t("now {0} \u00b0C", r1(w.temp)) : ""}${w.fallen ? " \u00b7 " + t("fallen {0} mm", r1(w.fallen)) : ""}</span>${w.error ? ` <span class="err">${esc(w.error)}</span>` : ""}</div>
      <div class="muted small">${t("Click a day for its runs.")}</div>
      <div class="fc" style="grid-template-columns:repeat(${Math.max(1, days.length)},1fr)">${days.map((x) => {
        const decs = (plan.runs || []).filter((r) => r.day === x.day).map((r) => this._decision(r, plan)).filter(Boolean);
        const sk = decs.some((v) => v.action === "skip" && v.status !== "dismissed" && v.status !== "none");
        const f = decs.find((v) => v.action === "adjust");
        return `<div class="fcd ${x.day === today ? "today" : ""} ${this._fday === x.day ? "sel" : ""}" data-act="fday" data-day="${x.day}" title="${esc(fmtDay(x.day))}"><span>${DAYS()[wd(x.day)]}</span>
          <ha-icon icon="mdi:weather-${WX_ICON[x.cond] || "cloudy"}"></ha-icon>
          <b>${x.tmax !== null && x.tmax !== undefined ? Math.round(x.tmax) + "\u00b0" : "\u2013"}</b><em>${x.tmin !== null && x.tmin !== undefined ? Math.round(x.tmin) + "\u00b0" : ""}</em>
          <span class="rain">${x.rain ? r1(x.rain) + " mm" : " "}</span>
          <span class="fx ${sk ? "skip" : f ? "adj" : ""}">${sk ? "\u2715" : f ? Math.round(f.factor * 100) + "%" : "100%"}</span></div>`;
      }).join("")}</div>`;
  }

  _dayPanel(plan) {
    const day = this._fday;
    if (!day) return "";
    const runs = (plan.runs || []).filter((r) => r.day === day);
    const user = new Set(plan.skipped || []); const wx = new Set(plan.weather_skipped || []); const sug = plan.suggestions || {};
    const now = this.data.now;
    const rows = runs.map((r) => {
      const k = runKey(r); const dec = this._decision(r, plan); const past = r.end < now;
      const answered = dec && (dec.status === "accepted" || dec.status === "dismissed");
      const B = [];
      if (!past) {
        if (user.has(k)) B.push(`<button class="ab" data-act="unskip" data-key="${esc(k)}"><ha-icon icon="mdi:undo"></ha-icon>${t("Undo skip")}</button>`);
        if (answered) B.push(`<button class="ab" data-act="sugreset" data-key="${esc(k)}"><ha-icon icon="mdi:undo"></ha-icon>${t(dec.status === "accepted" ? "Take back accept" : "Take back dismiss")}</button>`);
        else if (sug[k] || (dec && dec.status === "pending")) B.push(`<button class="ab" data-act="sugno" data-key="${esc(k)}">${t("Dismiss")}</button><button class="ab primary" data-act="sugyes" data-key="${esc(k)}">${t("Accept")}</button>`);
        if (wx.has(k) && !answered) B.push(`<button class="ab" data-act="unskip" data-key="${esc(k)}"><ha-icon icon="mdi:play"></ha-icon>${t("Run anyway")}</button>`);
        if (!user.has(k) && !wx.has(k)) B.push(`<button class="ab" data-act="skiprun" data-key="${esc(k)}"><ha-icon icon="mdi:skip-next-circle-outline"></ha-icon>${t("Skip")}</button>`);
      }
      const btns = B.join("");
      return `<div class="dprow ${past ? "past" : ""}">
        <span class="dpt"><b>${hm(r.start)}\u2013${hm(r.end)}</b> ${r.slots.map((x) => esc(this._slotName(x))).join(" + ")} ${this._runMark(r, plan)}</span>
        <span class="nz">${r.zones.map((z) => `<span>${this._mark(this._zone(z.zone))}${z.minutes}\u2032</span>`).join("")}</span>
        ${dec && dec.reasons.length ? `<span class="muted small">${esc(dec.reasons.join(", "))}</span>` : ""}
        <span class="dpb">${btns}</span></div>`;
    }).join("");
    return `<div class="box dpanel"><div class="lbl lrow">${fmtDay(day)}<span class="grow"></span><button class="xr" data-act="fday" data-day="${day}" title="${esc(t("Close"))}"><ha-icon icon="mdi:close"></ha-icon></button></div>
      ${rows || `<div class="muted">${t("No runs on this day.")}</div>`}</div>`;
  }

  _tab_week() {
    return `<div class="lbl">${t("Minutes per day")} <span class="muted">${t("(watered / planned)")}</span></div>${this._chart()}
      <div class="lbl">${t("Next 7 days")}</div><div data-preview="week"></div>
      <details class="runs" data-d="runs_week" ${this._open_("runs_week", false)}><summary>${t("Run details")}</summary><div data-preview="runs"></div></details>`;
  }

  _chart() {
    const d = this.data; const today = dayOf(d.now); const plan = this._plan(); const zones = this._zones();
    const hist = d.history || {}; const days = [];
    const blocked = this._blocked(plan);
    for (let i = -6; i <= 7; i++) days.push(addDays(today, i));
    const col = days.map((day) => {
      const per = {};
      if (day <= today) Object.entries(hist[day] || {}).forEach(([z, m]) => { per[z] = { done: m, plan: 0 }; });
      if (day >= today) (plan.runs || []).filter((r) => r.day === day && (day > today || r.start > d.now) && !blocked.has(runKey(r))).forEach((r) => r.zones.forEach((x) => {
        per[x.zone] = per[x.zone] || { done: 0, plan: 0 }; per[x.zone].plan += x.minutes; }));
      const total = Object.values(per).reduce((a, v) => a + v.done + v.plan, 0);
      return { day, per, total };
    });
    const max = Math.max(30, ...col.map((c) => c.total));
    return `<div class="chart">${col.map((c) => `<div class="cc ${c.day === today ? "today" : ""}" title="${fmtDay(c.day)}: ${fmtMin(c.total)}\n${zones.filter((z) => c.per[z.id]).map((z) => `${z.name}: ${Math.round(c.per[z.id].done)}${c.per[z.id].plan ? ` + ${Math.round(c.per[z.id].plan)} ${t("planned")}` : ""}`).join("\n")}">
        <div class="stack">${zones.filter((z) => c.per[z.id]).map((z) => `${c.per[z.id].done ? `<i style="height:${(c.per[z.id].done / max * 100).toFixed(1)}%;background:${z.color}"></i>` : ""}${c.per[z.id].plan ? `<i class="plan" style="height:${(c.per[z.id].plan / max * 100).toFixed(1)}%;--c:${z.color}"></i>` : ""}`).join("")}</div>
        <em>${c.total ? hmm(c.total) : ""}</em><span>${DAYS()[wd(c.day)]}</span></div>`).join("")}</div>
      ${this._legend(`<span><i class="plan" style="--c:#888"></i>${t("planned")}</span>`)}`;
  }

  // --- stats
  _tab_stats() {
    const d = this.data; const tot = d.stats_totals || {};
    const s = this._stats;
    if (!s) { this._loadStats(); }
    const tile = (label, x) => `<div class="stt"><div class="lbl">${t(label)}</div>
      <div class="sv">${fmtMin((x || {}).min)}</div>
      <div class="muted small">${x && x.l !== null && x.l !== undefined ? fmtL(x.l) + " \u00b7 " : ""}${x && x.kwh !== null && x.kwh !== undefined ? fmtKwh(x.kwh) + " \u00b7 " : ""}${(x || {}).runs || 0} ${t("runs")}${(x || {}).skips ? ` \u00b7 ${x.skips} ${t("skips")}` : ""}</div>
      ${this._cost(x) ? `<div class="cost">${esc(this._cost(x))}</div>` : ""}</div>`;
    const anyData = (tot.all || {}).min || (tot.all || {}).runs || (tot.all || {}).skips;
    if (!anyData) return `<div class="muted pad">${t("No statistics yet - they start with the first real run.")}</div>`;
    const rows = (s && s.rows) || [];
    const hasL = rows.some((r) => r.has_l); const hasK = rows.some((r) => r.has_kwh);
    let metric = this._sp.metric;
    if ((metric === "l" && !hasL) || (metric === "kwh" && !hasK)) metric = "min";
    const zones = this._zones();
    const val = (r, z) => (metric === "kwh" ? (z ? (r.zones[z] || {}).kwh || 0 : r.kwh) : ((r.zones[z] || {})[metric] || 0));
    const totalOf = (r) => (metric === "kwh" ? r.kwh : zones.reduce((a, z) => a + val(r, z.id), 0));
    const max = Math.max(1e-9, ...rows.map(totalOf));
    const fmtV = (v) => (metric === "min" ? fmtMin(v) : metric === "l" ? fmtL(v) : fmtKwh(v));
    const lbl = (k) => {
      if (this._sp.period === "day") return `${DAYS()[wd(k)]}<br>${+k.slice(8, 10)}.`;
      if (this._sp.period === "week") return k.slice(5);
      if (this._sp.period === "month") return (LANG === "sk" ? MON_SK : MON_EN)[+k.slice(5, 7) - 1];
      return k;
    };
    const chart = `<div class="chart tall">${rows.map((r) => {
      const tv = totalOf(r);
      const segs = metric === "kwh" ? (r.kwh ? `<i style="height:${(r.kwh / max * 100).toFixed(1)}%;background:#f5a524"></i>` : "")
        : zones.map((z) => { const v = val(r, z.id); return v ? `<i style="height:${(v / max * 100).toFixed(1)}%;background:${z.color}"></i>` : ""; }).join("");
      const tip = `${r.key}: ${fmtV(tv)}\n${metric === "kwh" ? "" : zones.filter((z) => val(r, z.id)).map((z) => `${z.name}: ${fmtV(val(r, z.id))}`).join("\n")}${r.skips ? `\n${r.skips} ${t("skips")}` : ""}`;
      return `<div class="cc" title="${esc(tip)}"><div class="stack">${segs}</div><em>${tv ? (metric === "min" ? hmm(tv) : metric === "l" ? Math.round(tv) : tv.toFixed(1)) : ""}</em><span>${lbl(r.key)}</span></div>`;
    }).join("")}</div>`;
    // per zone over the shown range
    const per = {}; let skMin = 0, allMin = 0, allL = 0;
    rows.forEach((r) => { skMin += r.skipped_min || 0; Object.entries(r.zones).forEach(([z, v]) => {
      const p = per[z] = per[z] || { min: 0, l: 0, kwh: 0, runs: 0, lmin: 0, emin: 0 };
      p.min += v.min || 0; p.l += v.l || 0; p.kwh += v.kwh || 0; p.runs += v.runs || 0; p.lmin += v.lmin || 0; p.emin += v.emin || 0; allMin += v.lmin || 0; allL += v.l || 0; }); });
    const usual = d.usual_flow || {};
    const maxMin = Math.max(1, ...Object.values(per).map((x) => x.min));
    const flowCell = (p, z) => { const avg = p.l && p.lmin ? r1(p.l / p.lmin) : null; const u = usual[z.id] ? r1(usual[z.id]) : null;
      return avg || u ? `${avg ?? "\u2013"}<span class="muted"> / ${u ?? "\u2013"}</span>` : "\u2013"; };
    const ztable = `<table class="zt st"><tr><th>${t("Zone")}</th><th>${t("Time")}</th><th class="r">${t("runs")}</th>
        ${hasL ? `<th class="r">${t("Water")}</th><th class="r" title="${esc(t("average / usual"))}">L/min</th>` : ""}${hasK ? `<th class="r">${t("Energy")}</th><th class="r">W</th>` : ""}</tr>
      ${zones.map((z) => { const p = per[z.id] || { min: 0, l: 0, kwh: 0, runs: 0 };
        return `<tr class="${p.min ? "" : "zero"}"><td class="zc">${this._mark(z)}${esc(z.name)}</td>
          <td><div class="tb"><span class="mbar"><i style="width:${(p.min / maxMin * 100).toFixed(0)}%;background:${z.color}"></i></span><span>${fmtMin(p.min)}</span></div></td><td class="r">${p.runs}</td>
          ${hasL ? `<td class="r">${p.l ? fmtL(p.l) : "\u2013"}</td><td class="r">${flowCell(p, z)}</td>` : ""}
          ${hasK ? `<td class="r">${p.kwh ? fmtKwh(p.kwh) : "\u2013"}</td><td class="r">${p.kwh && p.emin ? Math.round(p.kwh * 1000 / (p.emin / 60)) : "\u2013"}</td>` : ""}</tr>`; }).join("")}</table>`;
    const saved = skMin ? `<div class="muted small">${t("saved by skips")}: ${fmtMin(skMin)}${allL && allMin ? ` \u2248 ${fmtL(skMin * allL / allMin)}` : ""}</div>` : "";
    const sel = (k, opts) => `<span class="seg">${opts.map(([v, l, i]) => `<button class="ab ${String(this._sp[k]) === String(v) ? "on" : ""}" data-act="sp" data-k="${k}" data-v="${v}">${i ? `<ha-icon icon="${i}"></ha-icon>` : ""}${l}</button>`).join("")}</span>`;
    const allT = tot.all || {};
    return `${this._det("totals", false, `<ha-icon icon="mdi:sigma"></ha-icon><b>${t("Totals")}</b><span class="muted">${t("All time")}: ${fmtMin(allT.min)}${allT.l ? " \u00b7 " + fmtL(allT.l) : ""}${allT.kwh ? " \u00b7 " + fmtKwh(allT.kwh) : ""}</span>`,
      `<div class="stiles">${tile("This week", tot.week)}${tile("This month", tot.month)}${tile("This year", tot.year)}${tile("All time", tot.all)}</div>`)}
      <div class="abar wrapok"><select class="psel" data-sp="period">${[["day", t("per day")], ["week", t("per week")], ["month", t("per month")], ["year", t("per year")]].map(([v, l]) => `<option value="${v}" ${this._sp.period === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        <span class="grow"></span>${sel("metric", [["min", t("Time"), "mdi:timer-outline"], ...(hasL ? [["l", t("Water"), "mdi:water"]] : []), ...(hasK ? [["kwh", t("Energy"), "mdi:flash"]] : [])])}</div>
      ${s && s.error ? `<div class="err">${esc(s.error)}</div>` : chart}
      ${metric === "kwh" ? "" : this._legend()}
      <div class="lbl">${t("Last 12 months")}</div>${this._heatmap(metric)}
      <div class="lbl">${t("Per zone")}</div>${ztable}${saved}`;
  }

  _heatmap(metric) {
    const h = this._heat;
    if (!h) { if (!this._heatLoading) { this._heatLoading = true; this._ws({ type: `${DOMAIN}/stats`, period: "day", count: 371 }).then((x) => { this._heat = x; this._heatLoading = false; this._render(); }).catch(() => { this._heatLoading = false; }); } return `<div class="muted small">${t("Loading\u2026")}</div>`; }
    const rows = h.rows || [];
    const v = (r) => (metric === "kwh" ? r.kwh : metric === "l" ? r.l : r.min) || 0;
    const max = Math.max(1e-9, ...rows.map(v));
    const first = rows.length ? rows[0].key : dayOf(this.data.now);
    const pad = wd(first);
    const cells = Array(pad).fill(`<i class="hx"></i>`).concat(rows.map((r) => {
      const x = v(r); const lv = x ? Math.min(4, 1 + Math.floor(x / max * 3.999)) : 0;
      return `<i class="h${lv}" title="${fmtDay(r.key)} ${r.key.slice(0, 4)}: ${metric === "min" ? fmtMin(x) : metric === "l" ? fmtL(x) : fmtKwh(x)}${r.skips ? ` \u00b7 ${r.skips} ${t("skips")}` : ""}"></i>`;
    }));
    const months = []; let last = -1;
    const weeks = Math.ceil((rows.length + pad) / 7);
    rows.forEach((r, i) => { const mo = +r.key.slice(5, 7); if (mo !== last && +r.key.slice(8, 10) <= 7) { months.push(`<span style="grid-column:${Math.floor((i + pad) / 7) + 1} / span 4">${(LANG === "sk" ? MON_SK : MON_EN)[mo - 1]}</span>`); last = mo; } });
    return `<div class="heat" style="--w:${weeks}"><div class="hm">${months.join("")}</div><div class="hg">${cells.join("")}</div>
      <div class="hl muted small">${t("less")} <i class="h0"></i><i class="h1"></i><i class="h2"></i><i class="h3"></i><i class="h4"></i> ${t("more")}</div></div>`;
  }

  _tab_slots() {
    const zones = this._zones();
    const slots = this.draft.slots || [];
    const out = slots.map((s, i) => {
      const a = s.anchor || {};
      const open = this._open.has(i);
      const zin = new Map((s.zones || []).map((z) => [z.zone, z]));
      const when = `${a.mode === "finish" ? t("Finish by") : t("Start")} ${a.ref === "sunrise" ? t("sunrise") : a.ref === "sunset" ? t("sunset") : a.at || "?"}${a.offset ? ` ${a.offset > 0 ? "+" : ""}${a.offset}\u2032` : ""}`;
      const days = s.every_n_days ? t("every {0} days", s.every_n_days) : s.days && s.days.length < 7 ? s.days.map((x) => DAYS()[x]).join(" ") : t("every day");
      const k = (f) => `slots.${i}.${f}`;
      return `<div class="slot ${s.enabled === false ? "dis" : ""}">
        <div class="shead" data-act="toggle" data-i="${i}">
          <label class="sw" title="${t("enabled")}"><input type="checkbox" class="tog" data-k="${k("enabled")}" data-t="bool" ${s.enabled !== false ? "checked" : ""}></label>
          <span class="caret">${open ? "\u25be" : "\u25b8"}</span><b class="sn">${esc(s.name || s.id)}</b>
          <span class="muted ssum">${esc(when)} \u00b7 ${esc(days)}${s.reverse ? " \u00b7 " + t("reverse") : ""}</span>
          <span class="zicons">${(s.zones || []).map((z) => this._mark(this._zone(z.zone))).join("")}<em>${(s.zones || []).length}</em></span>
        </div>
        ${open ? `<div class="sbody">
          <div class="row"><label>${t("Name")} <input data-k="${k("name")}" value="${esc(s.name || "")}"></label>
            <label class="muted">id <code>${esc(s.id)}</code></label></div>
          <div class="row">
            <select data-k="${k("anchor.mode")}" data-r="1"><option value="start" ${a.mode !== "finish" ? "selected" : ""}>${t("Start at")}</option><option value="finish" ${a.mode === "finish" ? "selected" : ""}>${t("Finish by")}</option></select>
            <select data-k="${k("anchor.ref")}" data-r="1"><option value="time" ${!a.ref || a.ref === "time" ? "selected" : ""}>${t("time")}</option><option value="sunrise" ${a.ref === "sunrise" ? "selected" : ""}>${t("sunrise")}</option><option value="sunset" ${a.ref === "sunset" ? "selected" : ""}>${t("sunset")}</option></select>
            ${!a.ref || a.ref === "time" ? `<input type="time" data-k="${k("anchor.at")}" value="${esc(a.at || "05:00")}">` : ""}
            <label>${t("offset")} <input type="number" class="n" data-k="${k("anchor.offset")}" data-t="int" value="${esc(a.offset || 0)}"> min</label>
          </div>
          <div class="help">${t(a.mode === "finish" ? "help_finish" : "help_start")}${a.ref && a.ref !== "time" ? " " + t("help_offset_sun") : " " + t("help_offset_time")}</div>
          <div class="row">
            <select data-dm="${i}"><option value="days" ${s.every_n_days ? "" : "selected"}>${t("Weekdays")}</option><option value="every" ${s.every_n_days ? "selected" : ""}>${t("Every N days")}</option></select>
            ${s.every_n_days ? `<label>${t("every")} <input type="number" class="n" min="1" data-k="${k("every_n_days")}" data-t="int" value="${esc(s.every_n_days)}"> ${t("days from")} <input type="date" data-k="${k("every_n_from")}" value="${esc(s.every_n_from || dayOf(this.data.now))}"></label>`
              : `<span class="days">${DAYS().map((dn, di) => `<label class="day ${!s.days || s.days.includes(di) ? "on" : ""}"><input type="checkbox" data-day="${i}|${di}" ${!s.days || s.days.includes(di) ? "checked" : ""}>${dn}</label>`).join("")}</span>`}
          </div>
          <div class="row">
            <label><input type="checkbox" data-k="${k("reverse")}" data-t="bool" ${s.reverse ? "checked" : ""}> ${t("reverse ESP order")}</label>
            <label><input type="checkbox" data-k="${k("use_multiplier")}" data-t="bool" ${s.use_multiplier !== false ? "checked" : ""}> ${t("adjust by weather")}</label>
          </div>
          <div class="help">${t("help_reverse")} ${t("help_weather")}</div>
          <table class="zt"><tr><th></th><th>${t("Zone")}</th><th>${t("Minutes")}</th></tr>
            ${zones.map((z) => { const e = zin.get(z.id); const idx = (s.zones || []).findIndex((x) => x.zone === z.id);
              return `<tr class="${z.enabled ? "" : "dis"}"><td><input type="checkbox" data-zin="${i}|${esc(z.id)}" ${e ? "checked" : ""}></td>
                <td>${this._mark(z)}${esc(z.name)}${z.enabled ? "" : ` <span class='muted'>${t("(disabled)")}</span>`}</td>
                <td>${e ? `<input type="number" class="n" min="0.1" step="0.5" data-k="slots.${i}.zones.${idx}.minutes" data-t="num" value="${esc(e.minutes)}">${z.max_minutes ? ` <span class="muted">${t("max {0}", z.max_minutes)}</span>` : ""}${e.days ? ` <span class="muted">${t("own days")}: ${e.days.map((x) => DAYS()[x]).join(" ")}</span>` : ""}` : ""}</td></tr>`; }).join("")}
          </table>
          <div class="row"><button data-act="runslot1" data-slot="${esc(s.id)}">${t("Run now")}</button><span class="grow"></span><button class="danger" data-act="delslot" data-i="${i}">${t("Delete slot")}</button></div>
        </div>` : ""}
      </div>`;
    }).join("");
    return `${out || `<div class="muted pad">${t("No slots yet.")}</div>`}
      <div class="row"><button data-act="addslot">${t("+ Add slot")}</button></div>
      <div class="lbl">${t("Preview \u2013 next 7 days")} ${this.dirty ? t("(unsaved)") : ""}</div>
      <div data-preview="week"></div>
      <details class="runs" data-d="runs_slots" ${this._open_("runs_slots", false)}><summary>${t("Runs and conflicts")}</summary><div data-preview="runs"></div></details>`;
  }

  _zonesSection() {
    const zones = this._zones();
    return `<datalist id="iconlist">${ICONS.map((i) => `<option value="${i}"></option>`).join("")}</datalist>` + zones.map((z) => {
      const k = (f) => `zones.${z.id}.${f}`;
      const zc = this.draft.zones[z.id] || {};
      const follow = zc.weather !== false;
      const sum = `${this._mark(z, true)}<b>${esc(z.name)}</b><span class="muted">${t("ESP position {0}", z.order)}${z.enabled ? "" : " \u00b7 " + t("(disabled)")}${follow ? "" : " \u00b7 " + t("ignores weather")}${zc.max_per_run ? ` \u00b7 ${t("max per run")} ${zc.max_per_run}\u2032` : ""}</span>`;
      return this._det(`z_${z.id}`, false, sum, `
        <div class="row swatches">${[...new Set([...this._zones().map((x) => x.color), ...PALETTE, ...SWATCHES])].map((c) => `<button class="swc ${c.toLowerCase() === z.color.toLowerCase() ? "on" : ""}" data-act="setcolor" data-zone="${esc(z.id)}" data-color="${c}" style="background:${c}" title="${c}"></button>`).join("")}</div>
        <div class="row"><input type="color" data-k="${k("color")}" value="${esc(z.color)}" data-r="1">
          <input class="name" data-k="${k("name")}" value="${esc(zc.name || "")}" placeholder="${esc(z.name)}">
          <label><input type="checkbox" class="tog" data-k="${k("enabled")}" data-t="bool" data-r="1" ${z.enabled ? "checked" : ""}> ${t("use")}</label>
          <label title="${esc(t("Off for a greenhouse or indoor zone: the weather never shortens, lengthens or skips it."))}"><input type="checkbox" class="tog" data-k="${k("weather")}" data-t="bool" data-r="1" ${follow ? "checked" : ""}> ${t("follow weather")}</label>
          <span class="grow"></span><span class="muted">${z.max_minutes ? t("ESP max {0}\u2032", z.max_minutes) : ""}</span></div>
        <div class="row"><label>${t("icon")} <input class="icon" list="iconlist" data-k="${k("icon")}" data-r="1" value="${esc(zc.icon || "")}" placeholder="mdi:flower"></label>
          <span class="iconpick">${ICONS.slice(0, 16).map((i) => `<button class="ib ${zc.icon === i ? "on" : ""}" data-act="seticon" data-zone="${esc(z.id)}" data-icon="${i}" title="${i}"><ha-icon icon="${i}" style="color:${z.color}"></ha-icon></button>`).join("")}${zc.icon ? `<button class="x" data-act="seticon" data-zone="${esc(z.id)}" data-icon="">\u2715</button>` : ""}</span></div>
        <div class="row"><label>${t("max per run")} <input type="number" class="n" min="0" data-k="${k("max_per_run")}" data-t="num" value="${esc(zc.max_per_run ?? "")}"> min</label>
          <label>${t("max per day")} <input type="number" class="n" min="0" data-k="${k("max_per_day")}" data-t="num" value="${esc(zc.max_per_day ?? "")}"> min</label></div>`, "sub");
    }).join("");
  }

  _tab_settings() {
    const d = this.data; const st = this.draft.settings || {}; const p = this.draft.pump || {};
    const flags = d.flags || {};
    const services = (d.notify_services || []).filter((x) => x !== "notify.notify" && x !== "notify.send_message");
    const n = this.draft.notifications || {}; const full = d.notifications_full || { events: {} };
    const meta = d.notify_meta || { events: [], actions: {}, variables: {}, defaults: {} };
    const targets = new Set(n.targets || []);
    const ui = this.draft.ui || {};
    const w = { ...(d.weather_full || {}), ...(this.draft.weather || {}) };
    const wn = d.weather_now || {};
    const m = this.draft.meters || {};
    const unitRe = (re) => (e) => e.startsWith("sensor.") && re.test(this._unitOf(e));
    const svcName = (x) => (this._hass.states[x] ? this._fname(x) : x.slice(7).replace(/^mobile_app_/, "\ud83d\udcf1 "));
    const allSvc = [...new Set([...services, ...(n.targets || []), ...Object.values(n.events || {}).flatMap((e) => e.targets || [])])].sort();
    const recip = (list, kind, ev) => `<div class="svcs">${list.map((x) => { const known = services.includes(x);
        return `<span class="svc on ${known ? "" : "bad"}" title="${esc(x)}${known ? "" : " \u2013 " + t("missing")}">${esc(svcName(x))}
          <button class="tb1" data-act="testsvc" data-svc="${esc(x)}" title="${esc(t("Send test to {0}", x))}"><ha-icon icon="mdi:send"></ha-icon></button>
          <button class="xr" data-act="delsvc" data-kind="${kind}" data-ev="${ev || ""}" data-svc="${esc(x)}" title="${esc(t("Remove"))}"><ha-icon icon="mdi:close"></ha-icon></button></span>`; }).join("") || `<span class="muted">${t("nobody")}</span>`}
        <span class="addsvc"><input list="svclist" data-addsvc="${kind}|${ev || ""}" placeholder="${esc(t("+ add notify service"))}"><button class="ab" data-act="addsvc" data-kind="${kind}" data-ev="${ev || ""}"><ha-icon icon="mdi:plus"></ha-icon></button></span></div>`;
    const evRows = meta.events.map((ev) => {
      const e = { ...(meta.defaults[ev] || {}), ...((full.events || {})[ev] || {}), ...(((n.events || {})[ev]) || {}) };
      return `<details class="ev" data-d="ev_${ev}" ${this._open_("ev_" + ev, false)}><summary><label><input type="checkbox" data-ne="${ev}|enabled" ${e.enabled ? "checked" : ""}> ${esc(t(ev + "_ev"))}</label>
          <span class="muted">${esc(e.targets ? (e.targets.length ? e.targets.map(svcName).join(", ") : t("nobody")) : t("default recipients"))}</span>
          <span class="grow"></span><button class="tb1" data-act="testnotif" data-ev="${ev}" title="${esc(t("Send test"))}"><ha-icon icon="mdi:send"></ha-icon></button></summary>
        <div class="row"><label class="wide">${t("Title")} <input data-ne="${ev}|title" value="${esc(e.title || "")}"></label></div>
        <div class="row"><label class="wide">${t("Message")} <input data-ne="${ev}|message" value="${esc(e.message || "")}"></label></div>
        <div class="row"><label><input type="checkbox" data-nown="${ev}" ${e.targets ? "checked" : ""}> ${t("own recipients for this event")}</label></div>
        ${e.targets ? recip(e.targets, "ev", ev) : ""}
        ${ev === "planned" ? `<div class="row"><label>${t("minutes before")} <input type="number" class="n" data-ne="planned|lead" value="${esc(e.lead ?? 30)}"></label></div>` : ""}
        <div class="row">${t("Buttons")}: ${Object.entries(meta.actions).map(([a, l]) => `<label><input type="checkbox" data-na="${ev}|${a}" ${(e.actions || []).includes(a) ? "checked" : ""}> ${esc(t(l + "_a"))}</label>`).join("")}
          <span class="grow"></span><button class="ab" data-act="testnotif" data-ev="${ev}"><ha-icon icon="mdi:send"></ha-icon>${t("Send test")}</button></div>
        <div class="muted small">${t("Variables")}: ${(meta.variables[ev] || []).map((v) => `<code>{{ ${esc(v)} }}</code>`).join(" ")}. ${t("Android: icon, HTML, max 3 buttons. iOS: plain text.")}</div>
      </details>`;
    }).join("");
    const wk = (f) => `weather.${f}`;
    const sl = (f, dflt, mn, mx, st, u) => this._slider(wk(f), w[f] ?? dflt, mn, mx, st, u);
    const mode = w.mode || "off";
    const sec = (key, icon, title, sum, body, dflt) => this._det(key, dflt, `<ha-icon icon="${icon}"></ha-icon><b>${title}</b><span class="muted">${sum}</span>`, body);
    const modeName = { off: t("off"), suggest: t("suggest (Accept / Dismiss)"), auto: t("automatic") }[mode];
    const meterCount = ["flow", "water_total", "pump_power", "pump_energy"].filter((x) => m[x]).length;
    const mm = st.merge_mode || "window";
    const mergeNames = { window: "merge when closer than", overlap: "merge only when overlapping", shift: "never merge, shift the later run" };
    return `
      ${sec("s_planner", "mdi:tune-variant", t("Planner"), `${flags.enabled ? t("enabled") : t("off")}${flags.dry_run ? " \u00b7 " + t("Dry run") : ""}`, `
        <div class="row"><label><input type="checkbox" class="tog" data-flag="enabled" ${flags.enabled ? "checked" : ""}> ${t("Planner enabled")}</label>
          <label><input type="checkbox" class="tog" data-flag="dry_run" ${flags.dry_run ? "checked" : ""}> ${t("Dry run (send nothing to the ESP)")}</label></div>
        <div class="row"><label>${t("Name")} <input class="name" data-k="ui.title" value="${esc(ui.title || "")}" placeholder="${esc(d.title)}"></label>
          <label>${t("Language")} <select data-k="ui.language" data-r="1">${[["auto", t("automatic")], ["en", "English"], ["sk", "Slovensky"]].map(([v, l]) => `<option value="${v}" ${(ui.language || "auto") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>`, true)}
      ${sec("s_zones", "mdi:sprinkler", t("Zones"), t("{0} zones", this._zones().length), this._zonesSection(), false)}
      ${sec("s_merge", "mdi:call-merge", t("Merging slots"), `${t(mergeNames[mm])}${mm === "window" ? ` ${st.merge_window ?? 60} min` : ""}`, `
        <div class="row">
          <select data-k="settings.merge_mode" data-r="1">${Object.entries(mergeNames).map(([v, l]) => `<option value="${v}" ${mm === v ? "selected" : ""}>${t(l)}</option>`).join("")}</select>
          ${mm === "window" ? this._slider("settings.merge_window", st.merge_window ?? 60, 0, 240, 5, " min") : ""}
          <label>${t("same zone in both")} <select data-k="settings.same_zone">${["longer", "sum", "separate"].map((v) => `<option value="${v}" ${(st.same_zone || "longer") === v ? "selected" : ""}>${t(v)}</option>`).join("")}</select></label>
        </div>
        <div class="muted small">${t("Timing uses valve overlap {0} s (integration options) and pump delay {1} s.", d.timing.valve_overlap, d.timing.pump_delay)}</div>`, false)}
      ${sec("s_weather", "mdi:weather-partly-rainy", t("Weather"), `${modeName}${mode !== "off" && w.entity ? " \u00b7 " + esc(this._fname(w.entity)) : ""}`, `
        <div class="row"><label>${t("Mode")} <select data-k="${wk("mode")}" data-r="1">${[["off", t("off")], ["suggest", t("suggest (Accept / Dismiss)")], ["auto", t("automatic")]].map(([v, l]) => `<option value="${v}" ${mode === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          ${mode !== "off" ? `<span class="grow"></span><span class="muted small">${wn.updated ? t("forecast {0} \u00b7 {1} hourly items", hm(new Date(wn.updated).toLocaleString("sv").replace(" ", "T")), wn.hourly || 0) : ""}${wn.error ? ` <span class="err">${esc(wn.error)}</span>` : ""}</span><button data-act="wxrefresh">${t("Refresh")}</button>` : ""}</div>
        ${mode !== "off" ? `
        <div class="row"><span class="fl">${t("Forecast")}</span>${this._picker(wk("entity"), w.entity, (e) => e.startsWith("weather."), "wxlist", "weather.home")}</div>
        <div class="row"><span class="fl">${t("Rain sensor (fallen)")}</span>${this._picker(wk("rain_sensor"), w.rain_sensor, unitRe(/mm|in/), "rainlist")}</div>
        <div class="row"><span class="fl">${t("Temperature sensor")}</span>${this._picker(wk("temp_sensor"), w.temp_sensor, unitRe(/\u00b0|C$|F$/), "templist")}</div>
        <div class="row"><span class="fl">${t("Humidity sensor")}</span>${this._picker(wk("humidity_sensor"), w.humidity_sensor, unitRe(/^%$/), "humlist")}</div>
        <div class="row"><span class="fl">${t("Wind sensor")}</span>${this._picker(wk("wind_sensor"), w.wind_sensor, unitRe(/km\/h|m\/s|mph|kn/), "windlist")}</div>
        <div class="row"><span class="fl">${t("Gust sensor")}</span>${this._picker(wk("gust_sensor"), w.gust_sensor, unitRe(/km\/h|m\/s|mph|kn/), "gustlist")}</div>
        <div class="row"><span class="fl">${t("Raining now (binary or mm/h)")}</span>${this._picker(wk("rain_now"), w.rain_now, (e) => /^(binary_sensor|input_boolean)\./.test(e) || (e.startsWith("sensor.") && /mm\/h|in\/h/.test(this._unitOf(e))), "rnlist")}</div>
        <div class="grid">
          <span class="fl">${t("Skip when rain reaches")}</span>${sl("skip_rain", 4, 0, 20, 0.5, " mm")}
          <span class="fl">${t("count forecast")}</span>${sl("window", 12, 0, 48, 1, " h")}
          <span class="fl">${t("only hours with probability \u2265")}</span>${sl("min_probability", 50, 0, 100, 5, " %")}
          <span class="fl">${t("skip at wind \u2265")}</span>${sl("skip_wind", 40, 0, 80, 5, " km/h")}
          <span class="fl">${t("skip at gusts \u2265")}</span>${sl("skip_gust", 60, 0, 120, 5, " km/h")}
          <span class="fl">${t("skip below")} ${t("\u00b0C (frost)")}</span>${sl("skip_cold", 4, -5, 15, 1, " \u00b0C")}
          <span class="fl">${t("100 % at a daily max of")}</span>${sl("base_temp", 22, 10, 35, 1, " \u00b0C")}
          <span class="fl">${t("change per degree")}</span>${sl("per_degree", 4, 0, 10, 0.5, " %")}
          <span class="fl">${t("at least")}</span>${sl("min_factor", 50, 0, 100, 5, " %")}
          <span class="fl">${t("at most")}</span>${sl("max_factor", 160, 100, 250, 5, " %")}
          ${mode === "suggest" ? `<span class="fl">${t("suggest for runs within")}</span>${sl("horizon", 24, 1, 72, 1, " h")}
          <span class="fl">${t("When the forecast changes after I answered")}</span><select data-k="${wk("answers")}" data-r="1">${[["keep", t("keep my answer as it was")], ["follow", t("follow the new forecast, ask again if it changes")]].map(([v, l]) => `<option value="${v}" ${(w.answers || "keep") === v ? "selected" : ""}>${l}</option>`).join("")}</select>` : ""}
        </div>
        <div class="row"><label><input type="checkbox" class="tog" data-k="${wk("scale_rain")}" data-t="bool" ${w.scale_rain !== false ? "checked" : ""}> ${t("less rain reduces the minutes")}</label></div>
        <div class="muted small">${t("Zones with follow weather off are never changed.")}</div>` : ""}`, false)}
      ${sec("s_pump", "mdi:pump", t("Pump"), p.entity ? esc(this._fname(p.entity)) : "\u2013", `
        <div class="row">${this._picker("pump.entity", p.entity, (e) => /^(switch|input_boolean|light|fan)\./.test(e), "pumplist")}</div>
        ${p.entity ? `<div class="row"><label><input type="checkbox" class="tog" data-k="pump.auto_on" data-t="bool" ${p.auto_on !== false ? "checked" : ""}> ${t("on before a run")}</label>
          <label><input type="checkbox" class="tog" data-k="pump.auto_off" data-t="bool" ${p.auto_off !== false ? "checked" : ""}> ${t("off after")}</label>
          <label><input type="checkbox" class="tog" data-k="pump.warn_if_off" data-t="bool" ${p.warn_if_off !== false ? "checked" : ""}> ${t("warn if off")}</label></div>
        <div class="grid"><span class="fl">${t("then wait")}</span>${this._slider("pump.delay", p.delay || 0, 0, 120, 1, " s")}</div>` : ""}`, false)}
      ${sec("s_meters", "mdi:gauge", t("Meters (optional)"), meterCount ? `${meterCount} / 4` : "\u2013", `
        <div class="row"><span class="fl">${t("Water flow")}</span>${this._picker("meters.flow", m.flow, unitRe(/\/(min|h|s)$/), "flowlist", "L/min, m\u00b3/h")}</div>
        <div class="row"><span class="fl">${t("Water meter (total)")}</span>${this._picker("meters.water_total", m.water_total, unitRe(/^(L|m\u00b3|m3|gal)$/), "wtlist", "L, m\u00b3")}</div>
        <div class="row"><span class="fl">${t("Pump power")}</span>${this._picker("meters.pump_power", m.pump_power, unitRe(/^k?W$/), "pwlist", "W")}</div>
        <div class="row"><span class="fl">${t("Pump energy (total)")}</span>${this._picker("meters.pump_energy", m.pump_energy, unitRe(/^k?Wh$/), "enlist", "kWh")}</div>
        <div class="grid"><span class="fl">${t("warn when a zone's flow differs by")}</span>${this._slider("meters.flow_warn", m.flow_warn ?? 30, 0, 100, 5, " %")}</div>
        <div class="row"><b>${t("Prices")}</b>
          <label>${t("water per m\u00b3")} <input type="number" class="n" min="0" step="0.01" data-k="meters.water_price" data-t="num" value="${esc(m.water_price ?? "")}"> ${esc(this._cur())}</label>
          <label>${t("energy per kWh")} <input type="number" class="n" min="0" step="0.01" data-k="meters.energy_price" data-t="num" value="${esc(m.energy_price ?? "")}"> ${esc(this._cur())}</label></div>
        <div class="muted small">${t("Totals are preferred; without them the rate is integrated while a zone is open.")}</div>`, false)}
      ${sec("s_notify", "mdi:bell-outline", t("Notifications"), (n.targets || []).map((x) => esc(x.slice(7))).join(", ") || t("nobody"), `
        <div class="row"><b>${t("Send to")}</b> <span class="muted">${t("(default for every event, pick any number)")}</span></div>
        ${recip(n.targets || [], "default")}
        <datalist id="svclist">${services.filter((x) => !(n.targets || []).includes(x)).map((x) => `<option value="${esc(x)}">${esc(svcName(x))}</option>`).join("")}</datalist>
        <div class="muted small">${t("Any notify service or notify entity, e.g. notify.mobile_app_stefan and notify.mobile_app_wife. Each chip sends a test to just that one.")}</div>
        ${evRows}`, false)}`;
  }

  // ------------------------------------------------------------------ events
  _setPath(path, value) {
    const parts = path.split("."); let o = this.draft;
    for (let i = 0; i < parts.length - 1; i++) {
      const k = parts[i];
      if (o[k] === undefined || o[k] === null) o[k] = /^\d+$/.test(parts[i + 1]) ? [] : {};
      o = o[k];
    }
    const last = parts[parts.length - 1];
    if (value === null || value === "") delete o[last]; else o[last] = value;
  }

  _onInput(e, isChange) {
    const t0 = e.target;
    if (t0.dataset.sp !== undefined) {
      if (!isChange) return;
      this._sp[t0.dataset.sp] = t0.dataset.sp === "count" ? +t0.value : t0.value;
      if (t0.dataset.sp === "period") this._sp.count = { day: 14, week: 12, month: 12, year: 5 }[t0.value];
      if (t0.dataset.sp === "metric") this._render(); else this._loadStats();
      return;
    }
    if (t0.dataset.qz !== undefined || t0.dataset.qm !== undefined || t0.dataset.qrev !== undefined) {
      if (t0.dataset.qz !== undefined) { this._qr.sel[t0.dataset.qz] = t0.checked; if (isChange) this._render(); }
      else if (t0.dataset.qm !== undefined) { this._qr.min[t0.dataset.qm] = num(t0.value); if (t0.value) this._qr.sel[t0.dataset.qm] = true; if (isChange) this._render(); }
      else this._qr.reverse = t0.checked;
      return;
    }
    if (t0.dataset.k !== undefined) {
      if (!isChange && (t0.type === "checkbox" || t0.tagName === "SELECT" || t0.type === "color")) return;
      let v = t0.type === "checkbox" ? t0.checked : t0.value;
      if (t0.type === "range" && t0.nextElementSibling) t0.nextElementSibling.textContent = t0.value + (t0.dataset.u || "");
      const ty = t0.dataset.t;
      if (ty === "num") v = num(v);
      else if (ty === "int") v = v === "" ? null : parseInt(v, 10);
      this._setPath(t0.dataset.k, v);
      if (t0.dataset.k === "ui.title") { const h = this.shadowRoot.querySelector(".head .title"); if (h) h.textContent = this._title(); }
      this._markDirty(isChange && t0.dataset.r === "1");
      return;
    }
    if (t0.dataset.pick !== undefined) {
      if (!isChange) return;
      const v = t0.value.trim();
      const ok = !v || this._hass.states[v];
      t0.classList.toggle("bad", !ok);
      if (ok) { this._editing = null; this._setPath(t0.dataset.pick, v || null); this._markDirty(true); }
      return;
    }
    if (!isChange) {
      if (t0.dataset.ne && t0.type !== "checkbox") this._setEvent(t0.dataset.ne, t0.value, false);
      return;
    }
    if (t0.dataset.nown) {
      const ev = t0.dataset.nown; const n = this.draft.notifications; n.events = n.events || {}; n.events[ev] = n.events[ev] || {};
      if (t0.checked) n.events[ev].targets = (n.targets || []).slice(); else delete n.events[ev].targets;
      this._markDirty(true); return;
    }
    if (t0.dataset.nev) {
      const [ev, svc] = t0.dataset.nev.split("|"); const n = this.draft.notifications; n.events = n.events || {}; n.events[ev] = n.events[ev] || {};
      const cur = n.events[ev].targets || [];
      n.events[ev].targets = t0.checked ? [...new Set([...cur, svc])] : cur.filter((x) => x !== svc);
      this._markDirty(true); return;
    }
    if (t0.dataset.day) {
      const [i, di] = t0.dataset.day.split("|").map(Number); const s = this.draft.slots[i];
      let days = s.days ? s.days.slice() : [0, 1, 2, 3, 4, 5, 6];
      days = t0.checked ? [...new Set([...days, di])].sort() : days.filter((x) => x !== di);
      s.days = days.length === 7 ? null : days;
      if (s.days === null) delete s.days;
      this._markDirty(true);
    } else if (t0.dataset.dm) {
      const s = this.draft.slots[+t0.dataset.dm];
      if (t0.value === "every") { s.every_n_days = 2; s.every_n_from = dayOf(this.data.now); } else { delete s.every_n_days; delete s.every_n_from; }
      this._markDirty(true);
    } else if (t0.dataset.zin) {
      const [i, zid] = t0.dataset.zin.split("|"); const s = this.draft.slots[+i];
      s.zones = s.zones || [];
      if (t0.checked) s.zones.push({ zone: zid, minutes: 10 }); else s.zones = s.zones.filter((z) => z.zone !== zid);
      this._markDirty(true);
    } else if (t0.dataset.nt) {
      const n = this.draft.notifications; n.targets = n.targets || [];
      n.targets = t0.checked ? [...new Set([...n.targets, t0.dataset.nt])] : n.targets.filter((x) => x !== t0.dataset.nt);
      this._markDirty(true);
    } else if (t0.dataset.ne) {
      this._setEvent(t0.dataset.ne, t0.type === "checkbox" ? t0.checked : t0.value, true);
    } else if (t0.dataset.na) {
      const [ev, a] = t0.dataset.na.split("|");
      const cur = this._eventValue(ev, "actions") || [];
      this._setEvent(`${ev}|actions`, t0.checked ? [...new Set([...cur, a])] : cur.filter((x) => x !== a), true);
    } else if (t0.dataset.flag) {
      this._ws({ type: `${DOMAIN}/flag`, name: t0.dataset.flag, value: t0.checked }).then(() => this._load()).catch((err) => alert(err.message));
    }
  }

  _eventValue(ev, field) {
    const n = (this.draft.notifications.events || {})[ev] || {};
    if (n[field] !== undefined) return n[field];
    return (((this.data.notifications_full || {}).events || {})[ev] || {})[field];
  }

  _setEvent(spec, value, isChange) {
    const [ev, field] = spec.split("|");
    const n = this.draft.notifications; n.events = n.events || {}; n.events[ev] = n.events[ev] || {};
    if (field === "lead") n.events[ev].lead = parseInt(value, 10) || 0;
    else n.events[ev][field] = value;
    this._markDirty(false);
    void isChange;
  }

  async _onClick(e) {
    const tg = e.target.closest("[data-tab],[data-act]");
    if (!tg) return;
    if (tg.dataset.tab) { this._tab = tg.dataset.tab; if (this._tab === "stats") { this._stats = null; this._heat = null; } this._render(); return; }
    if (e.target.closest("label.sw, label.master")) return;     // switches inside clickable headers
    const act = tg.dataset.act;
    const svc = (s, data) => this._hass.callService(DOMAIN, s, { ...(this._cfg.entry_id ? { config_entry_id: this._cfg.entry_id } : {}), ...data });
    const real = () => !(this.data.flags || {}).dry_run;
    try {
      if (act === "toggle") { const i = +tg.dataset.i; this._open.has(i) ? this._open.delete(i) : this._open.add(i); this._render(); }
      else if (act === "addslot") {
        const ids = new Set(this.draft.slots.map((s) => s.id)); let n = this.draft.slots.length + 1; while (ids.has(`slot_${n}`)) n++;
        this.draft.slots.push({ id: `slot_${n}`, name: `Slot ${n}`, enabled: true, anchor: { mode: "start", ref: "time", at: "06:00" }, zones: [] });
        this._open.add(this.draft.slots.length - 1); this._markDirty(true);
      } else if (act === "delslot") {
        const i = +tg.dataset.i; if (!confirm(t("Delete slot \"{0}\"?", this.draft.slots[i].name || this.draft.slots[i].id))) return;
        this.draft.slots.splice(i, 1); this._open.clear(); this._markDirty(true);
      } else if (act === "editpick") { this._editing = tg.dataset.path; this._render(); const i = this.shadowRoot.querySelector(`[data-pick="${tg.dataset.path}"]`); if (i) i.focus();
      } else if (act === "clearpick") { this._setPath(tg.dataset.path, null); this._markDirty(true);
      } else if (act === "setcolor") { this._setPath(`zones.${tg.dataset.zone}.color`, tg.dataset.color); this._markDirty(true);
      } else if (act === "sp") { this._sp[tg.dataset.k] = tg.dataset.v;
        if (tg.dataset.k === "period") { this._sp.count = { day: 14, week: 12, month: 12, year: 5 }[tg.dataset.v]; this._loadStats(); } else this._render();
      } else if (act === "fday") { this._fday = this._fday === tg.dataset.day ? null : tg.dataset.day; this._render();
      } else if (act === "clearall") {
        e.preventDefault(); e.stopPropagation();
        if (!confirm(t("Undo all your skips and forget all weather answers?"))) return;
        await svc("clear_skips", { answers: true }); setTimeout(() => this._load(), 800);
      } else if (act === "skiprun") { await svc("skip_run", { run: tg.dataset.key }); setTimeout(() => this._load(), 800);
      } else if (act === "zview") { this._zv = tg.dataset.v; localStorage.setItem("esp_sprinkler_zview", this._zv); this._render();
      } else if (act === "seticon") { this._setPath(`zones.${tg.dataset.zone}.icon`, tg.dataset.icon || null); this._markDirty(true);
      } else if (act === "revert") { this.dirty = false; this.draft = this._makeDraft(this.data); this.preview = null; this._render(); }
      else if (act === "save") {
        try {
          this.data = await this._ws({ type: `${DOMAIN}/save`, config: this.draft });
          this._fetched = Date.now(); this.dirty = false; this.draft = this._makeDraft(this.data); this.preview = null; this._render();
        } catch (err) { this._saveErr = err.message || String(err); this._renderBar(); }
      } else if (act === "stop") { await svc("stop", {}); setTimeout(() => this._load(), 1500); }
      else if (act === "skip") { await svc("skip_next", {}); setTimeout(() => this._load(), 800); }
      else if (act === "unskip") { await svc("unskip", { run: tg.dataset.key }); setTimeout(() => this._load(), 800); }
      else if (act === "sugreset") { await svc("answer_suggestion", { run: tg.dataset.key, reset: true }); setTimeout(() => this._load(), 800); }
      else if (act === "sugyes" || act === "sugno") { await svc("answer_suggestion", { run: tg.dataset.key, accept: act === "sugyes" }); setTimeout(() => this._load(), 800); }
      else if (act === "wxrefresh") { await svc("refresh_weather", {}); setTimeout(() => this._load(), 1500); }
      else if (act === "qr") { this._qr = this._qr ? null : { sel: {}, min: {}, reverse: false }; this._render(); }
      else if (act === "qrcancel") { this._qr = null; this._render(); }
      else if (act === "qrrun") {
        const zones = this._zones().filter((z) => z.enabled && this._qr.sel[z.id]).map((z) => ({ zone: z.id, minutes: +this._qr.min[z.id] || 5 }));
        if (!zones.length) { alert(t("Pick at least one zone.")); return; }
        const total = zones.reduce((a, z) => a + z.minutes, 0);
        if (real() && !confirm(t("Dry run is OFF - this will really water for {0} min. Start now?", total))) return;
        await svc("quick_run", { zones, reverse: !!this._qr.reverse }); this._qr = null; setTimeout(() => this._load(), 2500);
      } else if (act === "runslot" || act === "runslot1") {
        if (this.dirty) { alert(t("Save the changes first.")); return; }
        const slot = act === "runslot" ? this.shadowRoot.getElementById("runslot").value : tg.dataset.slot;
        if (real() && !confirm(t("Dry run is OFF - this will really water. Start now?"))) return;
        await svc("run_slot", { slot }); setTimeout(() => this._load(), 2500);
      } else if (act === "runzone") {
        const m = num(this.shadowRoot.getElementById(`rz-${tg.dataset.zone}`).value);
        if (!m) return;
        if (real() && !confirm(t("Dry run is OFF - this will really water for {0} min. Start now?", m))) return;
        await svc("run_zone", { zone: tg.dataset.zone, minutes: m }); setTimeout(() => this._load(), 2500);
      } else if (act === "testnotif") {
        e.preventDefault(); e.stopPropagation();
        const ev = tg.dataset.ev; const n = this.draft.notifications || {}; const o = (n.events || {})[ev] || {};
        const targets = o.targets || n.targets || [];
        if (!targets.length) { alert(t("Pick at least one recipient.")); return; }
        const data = { event: ev, targets };
        for (const f of ["title", "message", "actions"]) { const v = this._eventValue(ev, f); if (v !== undefined && v !== null) data[f] = v; }
        const r = await this._hass.callService(DOMAIN, "test_notification", { ...(this._cfg.entry_id ? { config_entry_id: this._cfg.entry_id } : {}), ...data }, undefined, true, true);
        this._toast(t("Sent to {0}", (((r || {}).response || {}).sent_to || targets).join(", ")), tg);
      } else if (act === "testsvc") {
        e.preventDefault(); e.stopPropagation();
        await svc("test_notification", { event: "started", targets: [tg.dataset.svc] });
        this._toast(t("Sent to {0}", tg.dataset.svc), tg);
      } else if (act === "addsvc" || act === "delsvc") {
        const kind = tg.dataset.kind; const ev = tg.dataset.ev; const n = this.draft.notifications;
        n.events = n.events || {};
        const get = () => (kind === "ev" ? (n.events[ev] || {}).targets || [] : n.targets || []);
        const set = (l) => { if (kind === "ev") { n.events[ev] = n.events[ev] || {}; n.events[ev].targets = l; } else n.targets = l; };
        if (act === "delsvc") { set(get().filter((x) => x !== tg.dataset.svc)); this._markDirty(true); return; }
        const inp = this.shadowRoot.querySelector(`[data-addsvc="${kind}|${ev}"]`);
        const v = ((inp && inp.value) || "").trim();
        if (!/^notify\.[a-z0-9_]+$/.test(v)) { alert(t("A notify service looks like notify.mobile_app_phone")); return; }
        set([...new Set([...get(), v])]); this._markDirty(true);
      }
    } catch (err) { alert(err.message || String(err)); }
  }

  _toast(msg, near) {
    const el = document.createElement("div"); el.className = "toast"; el.textContent = msg;
    this.shadowRoot.querySelector("ha-card").appendChild(el); setTimeout(() => el.remove(), 2500); void near;
  }

  _moveNow() {
    if (!this.data) return;
    const now = this._nowIso();
    for (const el of this.shadowRoot.querySelectorAll(".mark.now")) el.style.left = `${(now.min / 14.4).toFixed(3)}%`;
    for (const el of this.shadowRoot.querySelectorAll(".prog")) {
      const s = +el.dataset.s, e = +el.dataset.e, n = Date.now();
      el.querySelector(".pfill").style.left = `${(Math.max(0, Math.min(1, (n - s) / Math.max(1, e - s))) * 100).toFixed(2)}%`;
      const pl = el.parentElement.querySelector(".pleft"); if (pl) pl.textContent = fmtMin(Math.max(0, Math.round((e - n) / 60000)));
    }
  }
}

const CSS = `
:host { display:block; }
ha-card { overflow:hidden; }
.wrap { padding:12px 14px 0; font-size:14px; color:var(--primary-text-color,#1c1c1c); }
.pad { padding:12px 0; }
.head { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.title { font-size:18px; font-weight:600; margin-right:auto; }
.hicon { --mdc-icon-size:26px; color:var(--primary-color,#03a9f4); } .hicon.off { color:var(--disabled-text-color,#888); }
.master { display:inline-flex; margin-left:4px; }
input.tog { appearance:none; -webkit-appearance:none; width:34px; height:18px; border-radius:9px; background:var(--divider-color,#bbb); position:relative; cursor:pointer; border:0; padding:0; margin:0 4px 0 0; flex:none; vertical-align:middle; transition:background .15s; }
input.tog::after { content:""; position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#fff; transition:left .15s; }
input.tog:checked { background:var(--primary-color,#03a9f4); } input.tog:checked::after { left:18px; }
details.sec { border:1px solid var(--divider-color,#ddd); border-radius:10px; margin:6px 0; }
details.sec > summary, details.sub > summary { list-style:none; cursor:pointer; display:flex; align-items:center; gap:8px; padding:9px 12px; }
details.sec > summary::-webkit-details-marker, details.sub > summary::-webkit-details-marker { display:none; }
details.sec > summary::after, details.sub > summary::after { content:"\u25b8"; margin-left:auto; color:var(--secondary-text-color,#888); }
details.sec[open] > summary::after, details.sub[open] > summary::after { content:"\u25be"; }
details.sec > summary ha-icon { --mdc-icon-size:20px; color:var(--primary-color,#03a9f4); }
details.sec > summary .muted, details.sub > summary .muted { font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.secb { padding:0 12px 8px; border-top:1px solid var(--divider-color,#eee); }
details.sub { border-bottom:1px solid var(--divider-color,#eee); } details.sub > summary { padding:7px 2px; } details.sub .secb { border:0; padding:0 2px 6px 26px; }
.sl { display:inline-flex; align-items:center; gap:8px; } .sl input[type=range] { width:200px; accent-color:var(--primary-color,#03a9f4); padding:0; border:0; background:none; }
.sl output { min-width:62px; font-variant-numeric:tabular-nums; font-weight:600; }
.grid { display:grid; grid-template-columns:minmax(150px,240px) 1fr; gap:6px 10px; align-items:center; margin:8px 0; }
.grid .fl { width:auto; }
details.skp > summary { cursor:pointer; margin:2px 0; } details.skp > summary .muted { margin-left:6px; }
.chip { font-size:11px; font-weight:600; padding:2px 8px; border-radius:10px; background:var(--secondary-background-color,#eee); color:var(--primary-text-color,#333); }
.chip.small { font-size:10px; padding:1px 6px; margin-left:4px; }
.chip.warn { background:#f5a52433; color:#c47a00; }
.chip.off, .st-disabled { background:#8883; }
.st-running { background:#2fbf7133; color:#1f9d5a; }
.st-dry_run, .st-scheduled { background:#4e9cf533; color:#3b82d6; }
.st-error { background:#e5484d33; color:#d0393e; }
.banner { margin:8px 0; padding:6px 10px; border-radius:8px; }
.err { color:#e5484d; } .banner.err { background:#e5484d1a; }
.tabs { display:flex; gap:2px; margin:10px 0 6px; border-bottom:1px solid var(--divider-color,#ddd); overflow-x:auto; }
.tab { background:none; border:0; padding:8px 12px; cursor:pointer; color:var(--secondary-text-color,#666); font:inherit; border-bottom:2px solid transparent; white-space:nowrap; }
.tab.on { color:var(--primary-color,#03a9f4); border-bottom-color:var(--primary-color,#03a9f4); font-weight:600; }
.body { padding-bottom:10px; }
.lbl { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--secondary-text-color,#777); margin:12px 0 6px; }
.lbl .muted, .lbl .err { text-transform:none; letter-spacing:0; font-weight:400; }
.muted { color:var(--secondary-text-color,#777); } .small { font-size:12px; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.box { background:var(--secondary-background-color,#f4f4f4); border-radius:10px; padding:8px 10px; margin:8px 0; }
.grid2 .box { margin:0; }
.box .lbl { margin-top:2px; }
.big { font-size:17px; font-weight:600; display:flex; align-items:center; gap:6px; }
.actions, .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:8px 0; }
.grow { flex:1; }
button, select, input { font:inherit; font-size:13px; }
button { border:1px solid var(--divider-color,#ccc); background:var(--card-background-color,#fff); color:var(--primary-text-color,#222); border-radius:8px; padding:5px 10px; cursor:pointer; }
button.primary { background:var(--primary-color,#03a9f4); color:#fff; border-color:transparent; }
button.danger { color:#e5484d; border-color:#e5484d66; }
button.x { padding:2px 7px; }
input, select { border:1px solid var(--divider-color,#ccc); border-radius:8px; padding:4px 8px; background:var(--card-background-color,#fff); color:var(--primary-text-color,#222); }
input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]), select { min-height:30px; box-sizing:border-box; }
select { appearance:none; -webkit-appearance:none; padding-right:28px; cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24'%3E%3Cpath fill='%23888' d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
  background-repeat:no-repeat; background-position:right 8px center; background-size:16px; }
select:hover, input:not([type=checkbox]):not([type=range]):hover { border-color:var(--secondary-text-color,#999); } select:focus, input:focus { outline:none; border-color:var(--primary-color,#03a9f4); }
select option { background:var(--card-background-color,#fff); color:var(--primary-text-color,#222); }
@supports (appearance: base-select) {
  select { appearance:base-select; background-image:none; padding-right:8px; display:inline-flex; align-items:center; gap:6px; }
  select::picker-icon { content:"\u25be"; color:var(--secondary-text-color,#888); transition:rotate .15s; } select:open::picker-icon { rotate:180deg; }
  select::picker(select) { appearance:base-select; border:1px solid var(--divider-color,#444); border-radius:10px; padding:4px; background:var(--card-background-color,#fff); box-shadow:0 6px 18px #0006; }
  select option { border-radius:6px; padding:6px 10px; } select option:hover { background:var(--secondary-background-color,#eee); }
  select option:checked { background:color-mix(in srgb, var(--primary-color,#03a9f4) 18%, transparent); color:var(--primary-color,#03a9f4); font-weight:600; }
  select option::checkmark { content:""; }
}
.ag select { border:0; min-height:0; }
input.n { width:64px; } input.name { width:180px; } input.icon { width:170px; } input[type=color] { width:34px; height:26px; padding:1px; }
label.wide { flex:1; display:flex; gap:6px; align-items:center; } label.wide input { flex:1; }
.fl { width:190px; flex:none; color:var(--secondary-text-color,#777); }
.dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; flex:none; }
ha-icon.zi { --mdc-icon-size:16px; margin-right:4px; flex:none; } ha-icon.zi.big { --mdc-icon-size:20px; }
.tl { position:relative; height:46px; background:var(--secondary-background-color,#f2f2f2); border-radius:8px; margin-bottom:16px; }
.tl.compact { height:20px; margin-bottom:0; border-radius:5px; }
.run { position:absolute; top:6px; bottom:6px; display:flex; border-radius:4px; overflow:hidden; box-shadow:0 0 0 1px #0002; cursor:default; }
.tl.compact .run { top:3px; bottom:3px; }
.run i { display:block; min-width:1px; } .run.merged { box-shadow:0 0 0 2px var(--primary-color,#03a9f4); } .run.skipped { opacity:.3; }
.run.wx { box-shadow:0 0 0 1px #4e9cf5; background:repeating-linear-gradient(135deg,#4e9cf5 0 2px,transparent 2px 5px); }
.mark { position:absolute; top:0; bottom:0; width:2px; } .mark.sunrise { background:#f5a524aa; } .mark.sunset { background:#a970ffaa; } .mark.now { background:#e5484d; z-index:2; }
.ticks { position:absolute; left:0; right:0; bottom:-15px; height:14px; font-size:10px; color:var(--secondary-text-color,#888); }
.ticks span { position:absolute; transform:translateX(-2px); }
.wrow { display:flex; align-items:center; gap:8px; margin:4px 0; } .wday { width:66px; font-size:12px; flex:none; } .wtl { flex:1; }
.wwx { width:200px; flex:none; font-size:12px; display:grid; grid-template-columns:20px 30px 50px 1fr; align-items:center; white-space:nowrap; }
.wwx .wxi ha-icon { --mdc-icon-size:16px; } .wxt { text-align:right; padding-right:4px; } .wxm { display:flex; gap:3px; }
.rm { box-sizing:border-box; display:inline-flex; align-items:center; justify-content:center; gap:1px; width:46px; height:18px; font-size:11px; line-height:1; font-weight:700; border-radius:6px; padding:0 2px; border:1px solid transparent; background:var(--secondary-background-color,#eee); vertical-align:middle; white-space:nowrap; }
.rm.ok { color:#2fbf71; } .rm.skip { color:#fff; background:#e5484d; } .rm.adj { color:#fff; background:#c47a00; } .rm.user { color:var(--secondary-text-color,#888); }
.rm.sug ha-icon { width:11px; height:11px; display:inline-flex; --mdc-icon-size:11px; overflow:hidden; }
.rm.sug { background:transparent; border:1px dashed currentColor; cursor:pointer; } .rm.sug:hover { background:currentColor; } .rm.sug:hover, .rm.sug:hover ha-icon { color:#fff !important; }
.rm.sug ha-icon { --mdc-icon-size:12px; } .rm.sug.skip { color:#e5484d; } .rm.sug.adjust { color:#c47a00; }
.wx ha-icon { --mdc-icon-size:16px; vertical-align:-3px; margin-right:2px; } .rain { color:#4e9cf5; }
.legend { display:flex; gap:10px; flex-wrap:wrap; margin:8px 0; font-size:12px; align-items:center; } .legend > span { display:inline-flex; align-items:center; } .legend i { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:4px; }
.list { list-style:none; padding:0; margin:4px 0; } .list li.past { opacity:.45; } .list li { padding:6px 0; border-bottom:1px solid var(--divider-color,#eee); } .note { font-size:12px; color:#c47a00; } .note.wxn { color:#4e9cf5; }
.list .muted { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.dis { opacity:.55; }
.slot { border:1px solid var(--divider-color,#ddd); border-radius:10px; margin:6px 0; }
.shead { display:grid; grid-template-columns:auto 12px minmax(70px,max-content) minmax(0,1fr) auto; align-items:center; gap:8px; padding:8px 10px; cursor:pointer; } .caret { width:12px; }
.ssum { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; } .sn { white-space:nowrap; }
.zicons { display:inline-flex; align-items:center; justify-content:flex-end; } .zicons em { font-style:normal; font-size:11px; color:var(--secondary-text-color,#888); margin-left:2px; }
.sbody { padding:0 10px 8px; border-top:1px solid var(--divider-color,#eee); }
.days { display:inline-flex; flex-wrap:nowrap; gap:4px; }
label.day { display:inline-grid; place-items:center; min-width:34px; height:26px; padding:0 4px; border-radius:13px; border:1px solid var(--divider-color,#ccc); font-size:12px; cursor:pointer; user-select:none; }
label.day input { display:none; } label.day.on { background:var(--primary-color,#03a9f4); border-color:transparent; color:#fff; font-weight:600; }
.help { font-size:12px; color:var(--secondary-text-color,#888); margin:-2px 0 8px; line-height:1.4; }
.box { position:relative; } .stopnow { position:absolute; top:8px; right:8px; padding:4px 10px; }
.rm.ans { cursor:pointer; } .rm.ans:hover { outline:2px solid var(--primary-text-color,#fff); outline-offset:-1px; }
.fcd { cursor:pointer; transition:box-shadow .1s; } .fcd:hover { box-shadow:0 0 0 1px var(--divider-color,#bbb); } .fcd.sel { box-shadow:0 0 0 2px var(--primary-color,#03a9f4); }
.dpanel { box-shadow:inset 3px 0 0 var(--primary-color,#03a9f4); }
.dprow { display:flex; flex-wrap:wrap; align-items:center; gap:6px 12px; padding:6px 0; border-top:1px solid var(--divider-color,#eee); } .dprow.past { opacity:.5; }
.dpt { display:inline-flex; align-items:center; gap:6px; } .dprow .nz { margin:0; } .dpb { margin-left:auto; display:inline-flex; gap:6px; } .dpb .ab { padding:4px 10px; }
.svc .xr { width:22px; height:22px; }
.zt { border-collapse:collapse; width:100%; margin:6px 0; } .zt td, .zt th { padding:3px 4px; text-align:left; border-bottom:1px solid var(--divider-color,#eee); font-weight:normal; } .zt th { font-size:11px; color:var(--secondary-text-color,#888); }
.zt td:first-child { white-space:nowrap; } .zt.st td { vertical-align:top; }
.mbar { height:4px; background:var(--divider-color,#ddd); border-radius:2px; margin-top:3px; width:110px; } .mbar i { display:block; height:100%; border-radius:2px; }
.zbox { border:1px solid var(--divider-color,#ddd); border-radius:10px; padding:4px 10px; margin:6px 0; }
.iconpick { display:inline-flex; gap:2px; flex-wrap:wrap; } .ib { padding:2px 3px; border-radius:6px; line-height:0; } .ib.on { border-color:var(--primary-color,#03a9f4); } .ib ha-icon { --mdc-icon-size:18px; }
.strip { display:flex; gap:4px; height:54px; align-items:flex-end; margin:4px 0 6px; }
.sc { flex:1; height:100%; position:relative; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; font-size:10px; color:var(--secondary-text-color,#888); }
.sb { width:70%; border-radius:3px 3px 0 0; min-height:1px; } .sc span { margin-top:2px; } .sc em { position:absolute; top:0; font-style:normal; }
details.ev { border:1px solid var(--divider-color,#ddd); border-radius:8px; padding:4px 8px; margin:4px 0; } details.ev summary { cursor:pointer; display:flex; gap:10px; align-items:center; }
code { font-size:11px; background:var(--secondary-background-color,#f2f2f2); padding:0 3px; border-radius:3px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:8px; }
.tile { background:var(--secondary-background-color,#f4f4f4); border-radius:10px; padding:8px 10px; }
.tile.on { box-shadow:0 0 0 2px #2fbf71; } .tn { font-weight:600; display:flex; align-items:center; gap:2px; margin-bottom:6px; }
.chip.run-on { background:#2fbf71; color:#fff; }
.pbar { display:flex; height:8px; border-radius:4px; overflow:hidden; background:var(--divider-color,#ddd); }
.pbar i { display:block; }
i.plan { background:repeating-linear-gradient(135deg, var(--c) 0 3px, transparent 3px 6px); opacity:.75; }
.tm { display:flex; align-items:baseline; gap:2px; font-size:12px; margin-top:4px; } .tm b { font-size:15px; }
.chart { display:flex; gap:3px; height:130px; align-items:stretch; margin:6px 0 2px; } .chart.tall { height:170px; }
.cc { flex:1; display:flex; flex-direction:column; align-items:center; font-size:10px; color:var(--secondary-text-color,#888); position:relative; min-width:0; text-align:center; }
.cc.today span { color:var(--primary-color,#03a9f4); font-weight:700; }
.stack { flex:1; width:72%; display:flex; flex-direction:column-reverse; border-bottom:1px solid var(--divider-color,#ccc); }
.stack i { display:block; width:100%; }
.cc em { font-style:normal; height:13px; } .cc span { margin-top:2px; }
details.runs { margin-top:8px; } details.runs summary { cursor:pointer; color:var(--secondary-text-color,#777); font-size:12px; font-weight:600; }
.svcs { display:flex; flex-wrap:wrap; gap:6px; margin:4px 0 8px; }
.svc { border:1px solid var(--divider-color,#ccc); border-radius:14px; padding:2px 10px 2px 4px; display:inline-flex; align-items:center; gap:4px; cursor:pointer; font-size:12px; }
.svc.on { border-color:var(--primary-color,#03a9f4); background:color-mix(in srgb, var(--primary-color,#03a9f4) 12%, transparent); }
input.picker { width:300px; } input.bad { border-color:#e5484d; }
.qgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:6px; margin:8px 0; }
.qz { display:flex; align-items:center; gap:4px; padding:4px 6px; border-radius:8px; border:1px solid var(--divider-color,#ccc); }
.qz.on { border-color:var(--primary-color,#03a9f4); } .qz input.n { margin-left:auto; width:56px; }
.sug { box-shadow:inset 3px 0 0 #4e9cf5; }
.fc { display:grid; grid-template-columns:repeat(7,1fr); gap:4px; }
.fcd { display:flex; flex-direction:column; align-items:center; gap:1px; padding:5px 2px; border-radius:8px; background:var(--secondary-background-color,#f4f4f4); font-size:12px; }
.fcd.today { box-shadow:0 0 0 1px var(--primary-color,#03a9f4); } .fcd ha-icon { --mdc-icon-size:22px; } .fcd em { font-style:normal; color:var(--secondary-text-color,#888); font-size:11px; }
.fcd .rain { font-size:11px; min-height:14px; } .fx { font-size:11px; font-weight:700; color:var(--secondary-text-color,#888); } .fx.adj { color:#c47a00; } .fx.skip { color:#e5484d; }
.stiles { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:8px; }
.stt { background:var(--secondary-background-color,#f4f4f4); border-radius:10px; padding:6px 10px; } .stt .lbl { margin:2px 0; } .sv { font-size:19px; font-weight:600; }
.abar { display:flex; flex-wrap:nowrap; gap:8px; align-items:center; margin:10px 0; overflow-x:auto; scrollbar-width:none; }
.abar > * { flex:none; }
.ab { display:inline-flex; align-items:center; gap:6px; padding:7px 12px; border-radius:18px; font-weight:500; }
.ab ha-icon { --mdc-icon-size:18px; } .ab.on { border-color:var(--primary-color,#03a9f4); color:var(--primary-color,#03a9f4); }
.ab .muted { font-weight:400; font-size:12px; }
.ag { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--divider-color,#ccc); border-radius:18px; padding:2px 2px 2px 10px; margin-left:auto; }
.seg { display:inline-flex; gap:4px; flex-wrap:wrap; } .seg .ab { padding:5px 11px; }
.abar.wrapok { flex-wrap:wrap; overflow:visible; }
.psel { font-weight:600; }
.ab.clr { padding:2px 10px; font-size:12px; text-transform:none; letter-spacing:0; font-weight:500; }
.ag > ha-icon { --mdc-icon-size:18px; color:var(--secondary-text-color,#888); } .agl { font-size:12px; color:var(--secondary-text-color,#888); }
.ag select { border:0; background:transparent; font-weight:600; } .ag .ab { padding:5px 9px; }
.nz { display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; font-size:12px; align-items:center; } .nz > span { display:inline-flex; align-items:center; }
.zbar { display:flex; height:6px; border-radius:3px; overflow:hidden; margin-top:8px; gap:1px; } .zbar i { display:block; }
.nz .more { cursor:default; } .nzt { margin-left:auto; }
.big .rm { font-size:11px; }
.prog { position:relative; height:10px; margin-top:8px; border-radius:5px; overflow:hidden; }
.psegs { display:flex; height:100%; opacity:.45; } .psegs i { display:block; }
.pfill { position:absolute; top:0; bottom:0; right:0; background:var(--secondary-background-color,#f4f4f4); opacity:.75; border-left:2px solid var(--primary-text-color,#fff); }
.live { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0 2px; }
.lc { display:inline-flex; align-items:center; gap:4px; padding:3px 10px 3px 7px; border-radius:14px; background:var(--secondary-background-color,#f4f4f4); font-size:13px; font-variant-numeric:tabular-nums; }
.lc ha-icon { --mdc-icon-size:17px; color:var(--primary-color,#03a9f4); }
.lrow { display:flex; align-items:center; gap:4px; } .vt { padding:1px 4px; line-height:0; border-radius:6px; } .vt ha-icon { --mdc-icon-size:16px; }
.vt.on { border-color:var(--primary-color,#03a9f4); color:var(--primary-color,#03a9f4); }
.zlist { display:flex; flex-direction:column; }
.zr { display:grid; grid-template-columns:minmax(120px,190px) 1fr 58px minmax(90px,130px); gap:10px; align-items:center; padding:5px 2px; border-bottom:1px solid var(--divider-color,#eee); font-size:13px; }
.zr.on .zn { color:#2fbf71; } .zn { display:flex; align-items:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-weight:500; }
.pbar.thin { height:6px; } .zm { text-align:right; font-variant-numeric:tabular-nums; } .zx { font-size:12px; text-align:right; white-space:nowrap; }
.swatches { gap:4px; } .swc { width:20px; height:20px; padding:0; border-radius:50%; border:2px solid transparent; }
.swc.on { border-color:var(--primary-text-color,#fff); box-shadow:0 0 0 1px #0006; }
.cost { font-weight:600; color:#c47a00; margin-top:2px; }
.boxoff { opacity:.7; } .struck { text-decoration:line-through; text-decoration-thickness:2px; color:var(--secondary-text-color,#888); }
.chip.offc { background:#e5484d; color:#fff; text-transform:none; letter-spacing:0; }
.zt.st { font-size:13px; } .zt.st td, .zt.st th { padding:6px 6px; vertical-align:middle; } .zt.st .r { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.zt.st tr.zero td { color:var(--secondary-text-color,#888); } .zt.st .zc { display:flex; align-items:center; }
.tb { display:flex; align-items:center; gap:8px; white-space:nowrap; } .tb .mbar { margin:0; flex:1; min-width:50px; max-width:160px; }
.echip { display:inline-flex; align-items:center; gap:8px; border:1px solid var(--divider-color,#ccc); border-radius:18px; padding:2px 3px 2px 4px; max-width:100%; }
.echip.bad { border-color:#e5484d; } .echip .en { border:0; background:none; display:inline-flex; align-items:center; gap:6px; padding:2px 4px; min-width:0; }
.echip .en ha-icon { --mdc-icon-size:18px; color:var(--primary-color,#03a9f4); } .enm { font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.eid { font-size:11px; color:var(--secondary-text-color,#888); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.echip .ev { font-size:12px; font-variant-numeric:tabular-nums; color:var(--secondary-text-color,#888); white-space:nowrap; }
.xr, .tb1 { width:26px; height:26px; border-radius:50%; padding:0; display:inline-grid; place-items:center; border:0; background:var(--secondary-background-color,#eee); flex:none; }
.xr ha-icon, .tb1 ha-icon { --mdc-icon-size:15px; } .xr:hover { background:#e5484d; color:#fff; } .tb1:hover { background:var(--primary-color,#03a9f4); color:#fff; }
.svc label { display:inline-flex; align-items:center; gap:4px; cursor:pointer; } .svc .tb1 { width:22px; height:22px; margin-left:2px; } .svc.bad { border-color:#e5484d; }
.addsvc { display:inline-flex; align-items:center; gap:4px; } .addsvc input { width:220px; border-radius:14px; } .addsvc .ab { padding:3px 7px; }
details.ev > summary { display:flex; align-items:center; gap:10px; } details.ev > summary .tb1 { width:24px; height:24px; }
.toast { position:absolute; left:50%; bottom:14px; transform:translateX(-50%); background:var(--primary-text-color,#222); color:var(--card-background-color,#fff); padding:6px 14px; border-radius:16px; font-size:13px; z-index:5; box-shadow:0 2px 8px #0005; }
ha-card { position:relative; }
.heat { width:100%; } .hm { display:grid; grid-template-columns:repeat(var(--w),1fr); gap:2px; font-size:10px; color:var(--secondary-text-color,#888); height:13px; white-space:nowrap; }
.hg { display:grid; grid-template-columns:repeat(var(--w),1fr); grid-template-rows:repeat(7,auto); grid-auto-flow:column; gap:2px; }
.hg i { display:block; width:100%; aspect-ratio:1; border-radius:2px; } .hl i { display:inline-block; width:10px; height:10px; border-radius:2px; }
.h0 { background:var(--secondary-background-color,#eee); } .h1 { background:#4e9cf555; } .h2 { background:#4e9cf599; } .h3 { background:#4e9cf5cc; } .h4 { background:#4e9cf5; } .hx { visibility:hidden; }
.hl { display:flex; align-items:center; gap:3px; margin-top:4px; }
.compact .cbody { display:flex; align-items:center; gap:12px; padding:4px 0 10px; }
.ring { --p:0; width:56px; height:56px; border-radius:50%; flex:none; display:grid; place-items:center; background:conic-gradient(var(--primary-color,#03a9f4) calc(var(--p)*1%), var(--secondary-background-color,#eee) 0); }
.ring > span { width:44px; height:44px; border-radius:50%; background:var(--card-background-color,#fff); display:grid; place-items:center; font-size:12px; font-weight:700; }
.ring ha-icon { --mdc-icon-size:24px; color:var(--primary-color,#03a9f4); }
.cinfo { flex:1; min-width:0; } .cinfo .big { font-size:16px; }
.bar { position:sticky; bottom:0; display:none; gap:8px; align-items:center; padding:8px 14px; margin:0 -14px; background:var(--card-background-color,#fff); border-top:1px solid var(--divider-color,#ddd); }
.bar.show { display:flex; }
@media (max-width:520px) { .zr { grid-template-columns:1fr 50px 50px; } .zr .zx { display:none; } .ag { margin-left:0; }  .grid2 { grid-template-columns:1fr; } .fl { width:auto; } .wwx { width:130px; grid-template-columns:18px 26px 0 1fr; } .wxr { display:none; } .grid { grid-template-columns:1fr; } .sl input[type=range] { width:150px; } }
`;

class EspSprinklerPlannerCompact extends EspSprinklerPlannerCard {
  getCardSize() { return 2; }
  _render() {
    const root = this.shadowRoot.querySelector(".wrap");
    if (!root) return;
    if (!this.data) { root.innerHTML = `<div class="pad err">${esc(this._loadErr || t("Loading\u2026"))}</div>`; return; }
    LANG = this._lang();
    root.classList.add("compact");
    const d = this.data; const plan = d.plan; const act = d.active; const next = this._nextRun(plan); const az = d.active_zone;
    const flags = d.flags || {};
    let ring = `<div class="ring"><span><ha-icon icon="mdi:sprinkler-variant"></ha-icon></span></div>`;
    let main = next ? `<div class="big">${fmtDay(next.day)} ${hm(next.start)} ${this._runMark(next, plan)}</div><div class="muted small">${next.slots.map((x) => esc(this._slotName(x))).join(" + ")} \u00b7 ${t("until {0}", hm(next.end))}</div>`
      : `<div class="big muted">\u2013</div>`;
    if (act) {
      const s = Date.parse(act.run.start), e = Date.parse(act.run.end);
      const f = Math.max(0, Math.min(1, (Date.now() - s) / Math.max(1, e - s)));
      ring = `<div class="ring" data-s="${s}" data-e="${e}" style="--p:${(f * 100).toFixed(1)}"><span>${Math.round(f * 100)}%</span></div>`;
      main = `<div class="big">${az ? `${this._mark(this._zone(az.zone), true)}${esc(az.name)}` : t("Running")}</div><div class="muted small">${t("run ends {0}", hm(act.run.end))}${act.dry_run ? " \u00b7 " + t("Dry run") : ""}</div>`;
    }
    root.innerHTML = `<div class="head"><ha-icon class="hicon ${flags.enabled ? "" : "off"}" icon="mdi:sprinkler-variant"></ha-icon>
        <div class="title">${esc(this._title())}</div>
        ${flags.dry_run ? `<span class="chip warn">${t("DRY RUN")}</span>` : ""}
        <label class="master"><input type="checkbox" class="tog" data-flag="enabled" ${flags.enabled ? "checked" : ""}></label></div>
      <div class="cbody">${ring}<div class="cinfo">${main}</div></div>
      ${this._liveRow()}
      <div class="abar">${act ? `<button class="ab danger" data-act="stop"><ha-icon icon="mdi:stop-circle"></ha-icon>${t("Stop")}</button>` : ""}
        <button class="ab ${this._qr ? "on" : ""}" data-act="qr"><ha-icon icon="mdi:play-speed"></ha-icon>${t("Quick run")}</button>
        ${next ? `<button class="ab" data-act="skip"><ha-icon icon="mdi:skip-next-circle-outline"></ha-icon>${t("Skip")}</button>` : ""}</div>
      ${this._qr ? this._quickRun() : ""}`;
  }
  _moveNow() {
    super._moveNow();
    for (const el of this.shadowRoot.querySelectorAll(".ring[data-s]")) {
      const s = +el.dataset.s, e = +el.dataset.e; const f = Math.max(0, Math.min(1, (Date.now() - s) / Math.max(1, e - s)));
      el.style.setProperty("--p", (f * 100).toFixed(1)); el.querySelector("span").textContent = `${Math.round(f * 100)}%`;
    }
  }
}

customElements.define("esp-sprinkler-planner-card", EspSprinklerPlannerCard);
customElements.define("esp-sprinkler-planner-compact", EspSprinklerPlannerCompact);
window.customCards = window.customCards || [];
window.customCards.push({ type: "esp-sprinkler-planner-card", name: "ESP Sprinkler Planner", description: "Plan, run and edit ESP sprinkler schedules." });
window.customCards.push({ type: "esp-sprinkler-planner-compact", name: "ESP Sprinkler Planner (compact)", description: "Next run, progress, quick run." });
