/* ESP Sprinkler Planner card - no build step, plain custom element.
 *
 *   type: custom:esp-sprinkler-planner-card
 *   entry_id: <optional, only with more than one planner>
 *   tab: today | week | slots | zones | settings   (optional start tab)
 */
const DOMAIN = "esp_sprinkler_planner";
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const PALETTE = ["#4e9cf5", "#2fbf71", "#f5a524", "#e5484d", "#a970ff", "#16c1c8", "#ff7ab6", "#c3e14b"];
const TABS = [["today", "Today"], ["week", "Week"], ["slots", "Slots"], ["zones", "Zones"], ["settings", "Settings"]];
const STATUS = { idle: "Idle", scheduled: "Scheduled", running: "Running", dry_run: "Dry run", disabled: "Disabled", error: "Error" };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hm = (iso) => (iso ? iso.slice(11, 16) : "\u2013");
const dayOf = (iso) => (iso ? iso.slice(0, 10) : "");
const minOfDay = (iso) => +iso.slice(11, 13) * 60 + +iso.slice(14, 16) + (+iso.slice(17, 19) || 0) / 60;
const clone = (o) => JSON.parse(JSON.stringify(o ?? null));
const fmtDay = (d) => { const x = new Date(d + "T12:00:00"); return `${DAYS[(x.getDay() + 6) % 7]} ${x.getDate()}.${x.getMonth() + 1}.`; };
const addDays = (d, n) => { const x = new Date(d + "T12:00:00"); x.setDate(x.getDate() + n); return x.toISOString().slice(0, 10); };
const runKey = (r) => `${r.day}|${r.slots.join("+")}`;
const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));

class EspSprinklerPlannerCard extends HTMLElement {
  setConfig(config) {
    this._cfg = config || {};
    this._tab = this._cfg.tab || "today";
    this._open = new Set();
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
    this._load();
    this._timer = setInterval(() => this._load(), 60000);
    this._tick = setInterval(() => this._moveNow(), 30000);
  }

  disconnectedCallback() { clearInterval(this._timer); clearInterval(this._tick); }
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
    } catch (err) {
      this._loadErr = err.message || String(err);
    }
    this._render();
  }

  _makeDraft(d) {
    const c = d.config || {};
    return {
      zones: clone(c.zones || {}), slots: clone(c.slots || []), settings: clone(c.settings || {}),
      pump: clone(c.pump || {}), notifications: clone(c.notifications || { targets: [], events: {} }),
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
  _zones() {
    const zc = (this.draft && this.draft.zones) || {};
    return (this.data.valves || []).slice().sort((a, b) => a.order - b.order).map((v, i) => ({
      ...v, name: (zc[v.id] && zc[v.id].name) || v.name || v.id,
      enabled: zc[v.id] && zc[v.id].enabled !== undefined ? zc[v.id].enabled : v.enabled !== false,
      color: (zc[v.id] && zc[v.id].color) || PALETTE[i % PALETTE.length],
    }));
  }

  _color(zid) { const z = this._zones().find((x) => x.id === zid); return z ? z.color : "#888"; }
  _plan() { return this.dirty && this.preview && !this.preview.error ? this.preview : this.data.plan; }
  _nowIso() {
    const elapsed = (Date.now() - (this._fetched || Date.now())) / 60000;
    const base = this.data.now; const m = minOfDay(base) + elapsed;
    return { day: dayOf(base), min: m };
  }
  _sun(day) { return (this.data.sun || []).find((s) => s.day === day) || {}; }
  _nextRun(plan) {
    const now = this.data.now; const skipped = new Set(plan.skipped || []);
    return (plan.runs || []).find((r) => r.start > now && !skipped.has(runKey(r)));
  }
  _slotName(id) { const s = (this.draft.slots || []).find((x) => x.id === id); return (s && s.name) || id; }

  // ------------------------------------------------------------------ rendering
  _render() {
    const root = this.shadowRoot.querySelector(".wrap");
    if (!root) return;
    if (!this.data) { root.innerHTML = `<div class="pad err">${esc(this._loadErr || "Loading\u2026")}</div>`; return; }
    const d = this.data;
    const flags = d.flags || {};
    root.innerHTML = `
      <div class="head">
        <div class="title">${esc(this._cfg.title || d.title)}</div>
        <span class="chip st-${esc(d.status)}">${esc(STATUS[d.status] || d.status)}</span>
        ${flags.dry_run ? `<span class="chip warn" title="Nothing is sent to the ESP">DRY RUN</span>` : ""}
        ${flags.enabled ? "" : `<span class="chip off">planner off</span>`}
      </div>
      ${d.error ? `<div class="banner err">${esc(d.error)}</div>` : ""}
      ${this._loadErr ? `<div class="banner err">${esc(this._loadErr)}</div>` : ""}
      <div class="tabs">${TABS.map(([k, l]) => `<button class="tab ${this._tab === k ? "on" : ""}" data-tab="${k}">${l}</button>`).join("")}</div>
      <div class="body">${this[`_tab_${this._tab}`]()}</div>
      <div class="bar"></div>`;
    this._renderBar();
    this._renderPreview();
  }

  _renderBar() {
    const bar = this.shadowRoot.querySelector(".bar");
    if (!bar) return;
    bar.innerHTML = this.dirty ? `
      <span class="grow">${this._saveErr ? `<span class="err">${esc(this._saveErr)}</span>` : "Unsaved changes"}</span>
      <button data-act="revert">Revert</button><button class="primary" data-act="save">Save</button>` : "";
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
    for (const r of plan.runs || []) {
      const sd = dayOf(r.start), ed = dayOf(r.end);
      if (sd !== day && ed !== day) continue;
      const s = sd === day ? minOfDay(r.start) : 0;
      const e = ed === day ? minOfDay(r.end) : 1440;
      if (e <= s) continue;
      const total = r.zones.reduce((a, z) => a + z.minutes, 0) || 1;
      const segs = r.zones.map((z) => `<i style="flex:${z.minutes};background:${this._color(z.zone)}" title="${esc(z.name)} ${z.minutes} min"></i>`).join("");
      const skipped = (plan.skipped || []).includes(runKey(r));
      const tip = `${hm(r.start)}\u2013${hm(r.end)} ${r.slots.map((x) => this._slotName(x)).join(" + ")}\n` + r.zones.map((z) => `${z.name}: ${z.minutes} min`).join("\n") + (r.notes.length ? "\n" + r.notes.join("\n") : "");
      bars.push(`<div class="run ${r.merged ? "merged" : ""} ${skipped ? "skipped" : ""}" style="left:${(s / 14.4).toFixed(3)}%;width:${Math.max(0.4, (e - s) / 14.4).toFixed(3)}%" title="${esc(tip)}">${segs}</div>`);
      void total;
    }
    const mark = (iso, cls, label) => (iso && dayOf(iso) === day ? `<div class="mark ${cls}" style="left:${(minOfDay(iso) / 14.4).toFixed(3)}%" title="${label} ${hm(iso)}"></div>` : "");
    const ticks = [0, 3, 6, 9, 12, 15, 18, 21].map((h) => `<span style="left:${(h * 60 / 14.4).toFixed(2)}%">${h}</span>`).join("");
    return `<div class="tl ${compact ? "compact" : ""}">
      ${mark(sun.sunrise, "sunrise", "Sunrise")}${mark(sun.sunset, "sunset", "Sunset")}
      ${now.day === day ? `<div class="mark now" style="left:${(now.min / 14.4).toFixed(3)}%"></div>` : ""}
      ${bars.join("")}
      ${compact ? "" : `<div class="ticks">${ticks}</div>`}
    </div>`;
  }

  _weekRows(plan, small) {
    if (plan.error) return `<div class="err">${esc(plan.error)}</div>`;
    const start = dayOf(this.data.now);
    let out = "";
    for (let i = 0; i < 7; i++) {
      const day = addDays(start, i);
      const runs = (plan.runs || []).filter((r) => r.day === day);
      const per = {};
      runs.forEach((r) => r.zones.forEach((z) => { per[z.name] = (per[z.name] || 0) + z.minutes; }));
      const sum = Object.entries(per).map(([n, m]) => `${esc(n)} ${Math.round(m)}`).join(" \u00b7 ");
      out += `<div class="wrow"><div class="wday">${fmtDay(day)}</div><div class="wtl">${this._timeline(day, plan, true)}${small ? "" : `<div class="wsum">${sum || "\u2013"}</div>`}</div></div>`;
    }
    return out + `<div class="legend">${this._zones().map((z) => `<span><i style="background:${z.color}"></i>${esc(z.name)}</span>`).join("")}</div>`;
  }

  _runsList(plan) {
    if (plan.error) return `<div class="banner err">${esc(plan.error)}</div>`;
    const conf = (plan.conflicts || []).map((c) => `<li class="err">${esc(c.day)}: ${esc(c.message)}</li>`).join("");
    const rows = (plan.runs || []).slice(0, 30).map((r) => `<li class="${r.end < this.data.now ? "past" : ""}">
        <b>${fmtDay(r.day)} ${hm(r.start)}\u2013${hm(r.end)}</b> ${r.slots.map((x) => esc(this._slotName(x))).join(" + ")}
        ${r.merged ? `<span class="chip small">merged</span>` : ""}${r.reverse ? `<span class="chip small">reverse</span>` : ""}
        <div class="muted">${r.zones.map((z) => `<span class="dot" style="background:${this._color(z.zone)}"></span>${esc(z.name)} ${z.minutes}\u2032`).join("  ")}</div>
        ${r.notes.length ? `<div class="note">${r.notes.map(esc).join("<br>")}</div>` : ""}</li>`).join("");
    return `${conf ? `<ul class="list">${conf}</ul>` : ""}<ul class="list">${rows || `<li class="muted">No runs in the next 7 days.</li>`}</ul>`;
  }

  // --- tabs
  _tab_today() {
    const d = this.data; const plan = d.plan; const next = this._nextRun(plan);
    const az = d.active_zone; const act = d.active;
    const zones = this._zones();
    const last = d.last_run || {};
    const today = dayOf(d.now);
    const todayHist = (d.history || {})[today] || {};
    const slots = this.draft.slots || [];
    return `
      <div class="grid2">
        <div class="box">
          <div class="lbl">Now</div>
          ${act ? `<div class="big">${az ? `<span class="dot" style="background:${this._color(az.zone)}"></span>${esc(az.name)}` : act.dry_run ? "Dry run" : "Starting\u2026"}</div>
                   <div class="muted">${az && az.until ? `until ${hm(az.until)} \u00b7 ` : ""}run ends ${hm(act.run.end)}</div>`
                : `<div class="big muted">Nothing running</div>`}
        </div>
        <div class="box">
          <div class="lbl">Next run</div>
          ${next ? `<div class="big">${fmtDay(next.day)} ${hm(next.start)}</div><div class="muted">${next.slots.map((x) => esc(this._slotName(x))).join(" + ")} \u00b7 until ${hm(next.end)}</div>`
                 : `<div class="big muted">\u2013</div>`}
        </div>
      </div>
      <div class="actions">
        ${act ? `<button class="danger" data-act="stop">Stop</button>` : ""}
        ${next ? `<button data-act="skip">Skip next</button>` : ""}
        ${slots.length ? `<select id="runslot">${slots.map((s) => `<option value="${esc(s.id)}">${esc(s.name || s.id)}</option>`).join("")}</select><button data-act="runslot">Run slot now</button>` : ""}
      </div>
      <div class="lbl">Today</div>
      ${this._timeline(today, plan, false)}
      <div class="lbl">Zones today</div>
      <div class="tiles">${zones.map((z) => {
        const sk = new Set(plan.skipped || []);
        const nx = (plan.runs || []).find((r) => r.start > d.now && !sk.has(runKey(r)) && r.zones.some((x) => x.zone === z.id));
        const zm = nx && nx.zones.find((x) => x.zone === z.id);
        const done = todayHist[z.id] || 0;
        const left = (plan.runs || []).filter((r) => r.day === today && r.start > d.now && !sk.has(runKey(r))).reduce((a, r) => a + ((r.zones.find((x) => x.zone === z.id) || {}).minutes || 0), 0);
        const tot = Math.max(done + left, 1);
        const on = az && az.zone === z.id;
        return `<div class="tile ${z.enabled ? "" : "dis"} ${on ? "on" : ""}" title="${esc(z.name)}: ${Math.round(done)} min watered today, ${Math.round(left)} min still planned today">
          <div class="tn"><span class="dot" style="background:${z.color}"></span>${esc(z.name)}${on ? ` <span class="chip small run-on">ON</span>` : ""}</div>
          <div class="pbar"><i style="width:${(done / tot * 100).toFixed(1)}%;background:${z.color}"></i><i class="plan" style="width:${(left / tot * 100).toFixed(1)}%;--c:${z.color}"></i></div>
          <div class="tm"><b>${Math.round(done)}</b>${left ? `<span class="muted"> +${Math.round(left)}</span>` : ""} min<span class="grow"></span>${nx ? `<span class="muted" title="next run">\u23f5 ${nx.day === today ? "" : fmtDay(nx.day) + " "}${hm(nx.start)} \u00b7 ${zm.minutes}\u2032</span>` : ""}</div>
        </div>`;
      }).join("")}</div>`;
  }

  _tab_week() {
    return `<div class="lbl">Minutes per day <span class="muted">(watered / planned)</span></div>${this._chart()}
      <div class="lbl">Next 7 days</div><div data-preview="week"></div>
      <details class="runs"><summary>Run details</summary><div data-preview="runs"></div></details>`;
  }

  _chart() {
    const d = this.data; const today = dayOf(d.now); const plan = this._plan(); const zones = this._zones();
    const hist = d.history || {}; const days = [];
    for (let i = -6; i <= 7; i++) days.push(addDays(today, i));
    const col = days.map((day) => {
      const per = {};
      if (day <= today) Object.entries(hist[day] || {}).forEach(([z, m]) => { per[z] = { done: m, plan: 0 }; });
      if (day >= today) (plan.runs || []).filter((r) => r.day === day && (day > today || r.start > d.now) && !(plan.skipped || []).includes(runKey(r))).forEach((r) => r.zones.forEach((x) => {
        per[x.zone] = per[x.zone] || { done: 0, plan: 0 }; per[x.zone].plan += x.minutes; }));
      const total = Object.values(per).reduce((a, v) => a + v.done + v.plan, 0);
      return { day, per, total };
    });
    const max = Math.max(30, ...col.map((c) => c.total));
    return `<div class="chart">${col.map((c) => `<div class="cc ${c.day === today ? "today" : ""}" title="${fmtDay(c.day)}: ${Math.round(c.total)} min\n${zones.filter((z) => c.per[z.id]).map((z) => `${z.name}: ${Math.round(c.per[z.id].done)}${c.per[z.id].plan ? ` + ${Math.round(c.per[z.id].plan)} planned` : ""}`).join("\n")}">
        <div class="stack">${zones.filter((z) => c.per[z.id]).map((z) => `${c.per[z.id].done ? `<i style="height:${(c.per[z.id].done / max * 100).toFixed(1)}%;background:${z.color}"></i>` : ""}${c.per[z.id].plan ? `<i class="plan" style="height:${(c.per[z.id].plan / max * 100).toFixed(1)}%;--c:${z.color}"></i>` : ""}`).join("")}</div>
        <em>${c.total ? Math.round(c.total) : ""}</em><span>${DAYS[(new Date(c.day + "T12:00:00").getDay() + 6) % 7].slice(0, 2)}</span></div>`).join("")}</div>
      <div class="legend">${zones.map((z) => `<span><i style="background:${z.color}"></i>${esc(z.name)}</span>`).join("")}<span><i class="plan" style="--c:#888"></i>planned</span></div>`;
  }

  _tab_slots() {
    const zones = this._zones();
    const slots = this.draft.slots || [];
    const out = slots.map((s, i) => {
      const a = s.anchor || {};
      const open = this._open.has(i);
      const zin = new Map((s.zones || []).map((z) => [z.zone, z]));
      const when = `${a.mode === "finish" ? "Finish by" : "Start"} ${a.ref === "sunrise" ? "sunrise" : a.ref === "sunset" ? "sunset" : a.at || "?"}${a.offset ? ` ${a.offset > 0 ? "+" : ""}${a.offset}\u2032` : ""}`;
      const days = s.every_n_days ? `every ${s.every_n_days} days` : s.days && s.days.length < 7 ? s.days.map((x) => DAYS[x]).join(" ") : "every day";
      const k = (f) => `slots.${i}.${f}`;
      return `<div class="slot ${s.enabled === false ? "dis" : ""}">
        <div class="shead" data-act="toggle" data-i="${i}">
          <span class="caret">${open ? "\u25be" : "\u25b8"}</span><b>${esc(s.name || s.id)}</b>
          <span class="muted">${esc(when)} \u00b7 ${esc(days)} \u00b7 ${(s.zones || []).length} zones${s.reverse ? " \u00b7 reverse" : ""}</span>
          <span class="grow"></span>
          <label class="sw" title="enabled"><input type="checkbox" data-k="${k("enabled")}" data-t="bool" ${s.enabled !== false ? "checked" : ""}></label>
        </div>
        ${open ? `<div class="sbody">
          <div class="row"><label>Name <input data-k="${k("name")}" value="${esc(s.name || "")}"></label>
            <label class="muted">id <code>${esc(s.id)}</code></label></div>
          <div class="row">
            <select data-k="${k("anchor.mode")}" data-r="1"><option value="start" ${a.mode !== "finish" ? "selected" : ""}>Start at</option><option value="finish" ${a.mode === "finish" ? "selected" : ""}>Finish by</option></select>
            <select data-k="${k("anchor.ref")}" data-r="1"><option value="time" ${!a.ref || a.ref === "time" ? "selected" : ""}>time</option><option value="sunrise" ${a.ref === "sunrise" ? "selected" : ""}>sunrise</option><option value="sunset" ${a.ref === "sunset" ? "selected" : ""}>sunset</option></select>
            ${!a.ref || a.ref === "time" ? `<input type="time" data-k="${k("anchor.at")}" value="${esc(a.at || "05:00")}">` : ""}
            <label>offset <input type="number" class="n" data-k="${k("anchor.offset")}" data-t="int" value="${esc(a.offset || 0)}"> min</label>
          </div>
          <div class="row">
            <select data-dm="${i}"><option value="days" ${s.every_n_days ? "" : "selected"}>Weekdays</option><option value="every" ${s.every_n_days ? "selected" : ""}>Every N days</option></select>
            ${s.every_n_days ? `<label>every <input type="number" class="n" min="1" data-k="${k("every_n_days")}" data-t="int" value="${esc(s.every_n_days)}"> days from <input type="date" data-k="${k("every_n_from")}" value="${esc(s.every_n_from || dayOf(this.data.now))}"></label>`
              : DAYS.map((dn, di) => `<label class="day"><input type="checkbox" data-day="${i}|${di}" ${!s.days || s.days.includes(di) ? "checked" : ""}>${dn}</label>`).join("")}
          </div>
          <div class="row">
            <label><input type="checkbox" data-k="${k("reverse")}" data-t="bool" ${s.reverse ? "checked" : ""}> reverse ESP order</label>
            <label><input type="checkbox" data-k="${k("use_multiplier")}" data-t="bool" ${s.use_multiplier !== false ? "checked" : ""}> use multiplier</label>
          </div>
          <table class="zt"><tr><th></th><th>Zone</th><th>Minutes</th></tr>
            ${zones.map((z) => { const e = zin.get(z.id); const idx = (s.zones || []).findIndex((x) => x.zone === z.id);
              return `<tr class="${z.enabled ? "" : "dis"}"><td><input type="checkbox" data-zin="${i}|${esc(z.id)}" ${e ? "checked" : ""}></td>
                <td><span class="dot" style="background:${z.color}"></span>${esc(z.name)}${z.enabled ? "" : " <span class='muted'>(disabled)</span>"}</td>
                <td>${e ? `<input type="number" class="n" min="0.1" step="0.5" data-k="slots.${i}.zones.${idx}.minutes" data-t="num" value="${esc(e.minutes)}">${z.max_minutes ? ` <span class="muted">max ${z.max_minutes}</span>` : ""}${e.days ? ` <span class="muted">own days: ${e.days.map((x) => DAYS[x]).join(" ")}</span>` : ""}` : ""}</td></tr>`; }).join("")}
          </table>
          <div class="row"><button data-act="runslot1" data-slot="${esc(s.id)}">Run now</button><span class="grow"></span><button class="danger" data-act="delslot" data-i="${i}">Delete slot</button></div>
        </div>` : ""}
      </div>`;
    }).join("");
    return `${out || `<div class="muted pad">No slots yet.</div>`}
      <div class="row"><button data-act="addslot">+ Add slot</button></div>
      <div class="lbl">Preview \u2013 next 7 days ${this.dirty ? "(unsaved)" : ""}</div>
      <div data-preview="week"></div>
      <details class="runs" open><summary>Runs and conflicts</summary><div data-preview="runs"></div></details>`;
  }

  _tab_zones() {
    const d = this.data; const days = []; const start = dayOf(d.now);
    for (let i = 6; i >= 0; i--) days.push(addDays(start, -i));
    const hist = d.history || {};
    const zones = this._zones();
    const maxM = Math.max(1, ...zones.flatMap((z) => days.map((x) => (hist[x] || {})[z.id] || 0)));
    return zones.map((z) => {
      const k = (f) => `zones.${z.id}.${f}`;
      const zc = this.draft.zones[z.id] || {};
      return `<div class="zbox ${z.enabled ? "" : "dis"}">
        <div class="row"><input type="color" data-k="${k("color")}" value="${esc(z.color)}">
          <input class="name" data-k="${k("name")}" value="${esc(zc.name || "")}" placeholder="${esc(z.name)}">
          <label><input type="checkbox" data-k="${k("enabled")}" data-t="bool" ${z.enabled ? "checked" : ""}> use</label>
          <span class="grow"></span><span class="muted">ESP position ${z.order}${z.max_minutes ? ` \u00b7 ESP max ${z.max_minutes}\u2032` : ""}</span></div>
        <div class="row"><label>max per run <input type="number" class="n" min="0" data-k="${k("max_per_run")}" data-t="num" value="${esc(zc.max_per_run ?? "")}"> min</label>
          <label>max per day <input type="number" class="n" min="0" data-k="${k("max_per_day")}" data-t="num" value="${esc(zc.max_per_day ?? "")}"> min</label>
          <span class="grow"></span><input type="number" class="n" min="0.1" step="0.5" id="rz-${esc(z.id)}" value="5"><button data-act="runzone" data-zone="${esc(z.id)}">Run now (min)</button></div>
        <div class="strip">${days.map((x) => { const m = (hist[x] || {})[z.id] || 0;
          return `<div class="sc" title="${fmtDay(x)}: ${Math.round(m)} min"><div class="sb" style="height:${Math.round(m / maxM * 100)}%;background:${z.color}"></div><span>${DAYS[(new Date(x + "T12:00:00").getDay() + 6) % 7].slice(0, 2)}</span><em>${m ? Math.round(m) : ""}</em></div>`; }).join("")}</div>
      </div>`;
    }).join("");
  }

  _tab_settings() {
    const d = this.data; const st = this.draft.settings || {}; const p = this.draft.pump || {};
    const flags = d.flags || {};
    const pumpCands = Object.keys(this._hass.states).filter((e) => /^(switch|input_boolean|light|fan)\./.test(e)).sort();
    const fname = (e) => ((this._hass.states[e] || {}).attributes || {}).friendly_name || e;
    const services = (d.notify_services || []).filter((x) => x !== "notify.notify" && x !== "notify.send_message");
    const n = this.draft.notifications || {}; const full = d.notifications_full || { events: {} };
    const meta = d.notify_meta || { events: [], actions: {}, variables: {}, defaults: {} };
    const targets = new Set(n.targets || []);
    const evRows = meta.events.map((ev) => {
      const e = { ...(meta.defaults[ev] || {}), ...((full.events || {})[ev] || {}), ...(((n.events || {})[ev]) || {}) };
      return `<details class="ev"><summary><label><input type="checkbox" data-ne="${ev}|enabled" ${e.enabled ? "checked" : ""}> ${esc(ev.replace("_", " "))}</label>
          <span class="muted">${esc(e.targets ? (e.targets.length ? e.targets.map((x) => x.slice(7)).join(", ") : "nobody") : "default recipients")}</span></summary>
        <div class="row"><label class="wide">Title <input data-ne="${ev}|title" value="${esc(e.title || "")}"></label></div>
        <div class="row"><label class="wide">Message <input data-ne="${ev}|message" value="${esc(e.message || "")}"></label></div>
        <div class="row"><label><input type="checkbox" data-nown="${ev}" ${e.targets ? "checked" : ""}> own recipients for this event</label></div>
        ${e.targets ? `<div class="svcs">${services.map((x) => `<label class="svc ${e.targets.includes(x) ? "on" : ""}"><input type="checkbox" data-nev="${ev}|${esc(x)}" ${e.targets.includes(x) ? "checked" : ""}>${esc(x.slice(7))}</label>`).join("")}</div>` : ""}
        ${ev === "planned" ? `<div class="row"><label>minutes before <input type="number" class="n" data-ne="planned|lead" value="${esc(e.lead ?? 30)}"></label></div>` : ""}
        <div class="row">Buttons: ${Object.entries(meta.actions).map(([a, l]) => `<label><input type="checkbox" data-na="${ev}|${a}" ${(e.actions || []).includes(a) ? "checked" : ""}> ${esc(l)}</label>`).join("")}
          <span class="grow"></span><button data-act="testnotif" data-ev="${ev}">Send test</button></div>
        <div class="muted small">Variables: ${(meta.variables[ev] || []).map((v) => `<code>{{ ${esc(v)} }}</code>`).join(" ")}. Android: icon, HTML, max 3 buttons. iOS: plain text.</div>
      </details>`;
    }).join("");
    return `
      <div class="lbl">Planner</div>
      <div class="row"><label><input type="checkbox" data-flag="enabled" ${flags.enabled ? "checked" : ""}> Planner enabled</label>
        <label><input type="checkbox" data-flag="dry_run" ${flags.dry_run ? "checked" : ""}> Dry run (send nothing to the ESP)</label></div>
      <div class="lbl">Merging slots</div>
      <div class="row">
        <select data-k="settings.merge_mode">${[["window", "merge when closer than"], ["overlap", "merge only when overlapping"], ["shift", "never merge, shift the later run"]].map(([v, l]) => `<option value="${v}" ${(st.merge_mode || "window") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        <label><input type="number" class="n" min="0" data-k="settings.merge_window" data-t="int" value="${esc(st.merge_window ?? 60)}"> min</label>
        <label>same zone in both <select data-k="settings.same_zone">${["longer", "sum", "separate"].map((v) => `<option ${(st.same_zone || "longer") === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      </div>
      <div class="muted small">Timing uses valve overlap ${d.timing.valve_overlap} s (integration options) and pump delay ${d.timing.pump_delay} s.</div>
      <div class="lbl">Pump</div>
      <div class="row"><input class="picker" list="pumplist" data-pick="pump.entity" value="${esc(p.entity || "")}" placeholder="type to search: pump, well, shelly\u2026">
        <datalist id="pumplist">${pumpCands.map((e) => `<option value="${esc(e)}">${esc(fname(e))}</option>`).join("")}</datalist>
        ${p.entity ? `<span class="muted">${esc(fname(p.entity))}</span><button data-act="nopump">\u2715</button>` : ""}</div>
      <div class="row">
        ${p.entity ? `<label><input type="checkbox" data-k="pump.auto_on" data-t="bool" ${p.auto_on !== false ? "checked" : ""}> on before a run</label>
          <label>then wait <input type="number" class="n" min="0" max="600" data-k="pump.delay" data-t="int" value="${esc(p.delay || 0)}"> s</label>
          <label><input type="checkbox" data-k="pump.auto_off" data-t="bool" ${p.auto_off !== false ? "checked" : ""}> off after</label>
          <label><input type="checkbox" data-k="pump.warn_if_off" data-t="bool" ${p.warn_if_off !== false ? "checked" : ""}> warn if off</label>` : ""}</div>
      <div class="lbl">Notifications</div>
      <div class="row"><b>Send to</b> <span class="muted">(default for every event, pick any number)</span></div>
      <div class="svcs">${services.map((x) => `<label class="svc ${targets.has(x) ? "on" : ""}"><input type="checkbox" data-nt="${esc(x)}" ${targets.has(x) ? "checked" : ""}>${esc(x.slice(7))}</label>`).join("") || `<span class="muted">no notify services</span>`}</div>
      ${evRows}`;
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
    const t = e.target;
    if (t.dataset.k !== undefined) {
      if (!isChange && (t.type === "checkbox" || t.tagName === "SELECT")) return;
      let v = t.type === "checkbox" ? t.checked : t.value;
      const ty = t.dataset.t;
      if (ty === "num") v = num(v);
      else if (ty === "int") v = v === "" ? null : parseInt(v, 10);
      this._setPath(t.dataset.k, v);
      this._markDirty(isChange && t.dataset.r === "1");
      return;
    }
    if (t.dataset.pick !== undefined) {
      if (!isChange) return;
      const v = t.value.trim();
      const ok = !v || this._hass.states[v];
      t.classList.toggle("bad", !ok);
      if (ok) { this._setPath(t.dataset.pick, v || null); this._markDirty(true); }
      return;
    }
    if (!isChange) {
      if (t.dataset.ne && t.type !== "checkbox") this._setEvent(t.dataset.ne, t.value, false);
      return;
    }
    if (t.dataset.nown) {
      const ev = t.dataset.nown; const n = this.draft.notifications; n.events = n.events || {}; n.events[ev] = n.events[ev] || {};
      if (t.checked) n.events[ev].targets = (n.targets || []).slice(); else delete n.events[ev].targets;
      this._markDirty(true); return;
    }
    if (t.dataset.nev) {
      const [ev, svc] = t.dataset.nev.split("|"); const n = this.draft.notifications; n.events = n.events || {}; n.events[ev] = n.events[ev] || {};
      const cur = n.events[ev].targets || [];
      n.events[ev].targets = t.checked ? [...new Set([...cur, svc])] : cur.filter((x) => x !== svc);
      this._markDirty(true); return;
    }
    if (t.dataset.day) {
      const [i, di] = t.dataset.day.split("|").map(Number); const s = this.draft.slots[i];
      let days = s.days ? s.days.slice() : [0, 1, 2, 3, 4, 5, 6];
      days = t.checked ? [...new Set([...days, di])].sort() : days.filter((x) => x !== di);
      s.days = days.length === 7 ? null : days;
      if (s.days === null) delete s.days;
      this._markDirty(false);
    } else if (t.dataset.dm) {
      const s = this.draft.slots[+t.dataset.dm];
      if (t.value === "every") { s.every_n_days = 2; s.every_n_from = dayOf(this.data.now); } else { delete s.every_n_days; delete s.every_n_from; }
      this._markDirty(true);
    } else if (t.dataset.zin) {
      const [i, zid] = t.dataset.zin.split("|"); const s = this.draft.slots[+i];
      s.zones = s.zones || [];
      if (t.checked) s.zones.push({ zone: zid, minutes: 10 }); else s.zones = s.zones.filter((z) => z.zone !== zid);
      this._markDirty(true);
    } else if (t.dataset.nt) {
      const n = this.draft.notifications; n.targets = n.targets || [];
      n.targets = t.checked ? [...new Set([...n.targets, t.dataset.nt])] : n.targets.filter((x) => x !== t.dataset.nt);
      this._markDirty(true);
    } else if (t.dataset.ne) {
      this._setEvent(t.dataset.ne, t.type === "checkbox" ? t.checked : t.value, true);
    } else if (t.dataset.na) {
      const [ev, a] = t.dataset.na.split("|");
      const cur = this._eventValue(ev, "actions") || [];
      this._setEvent(`${ev}|actions`, t.checked ? [...new Set([...cur, a])] : cur.filter((x) => x !== a), true);
    } else if (t.dataset.flag) {
      this._ws({ type: `${DOMAIN}/flag`, name: t.dataset.flag, value: t.checked }).then(() => this._load()).catch((err) => alert(err.message));
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
    if (field === "targets") {
      const list = String(value).split(",").map((x) => x.trim()).filter(Boolean);
      if (list.length) n.events[ev].targets = list; else delete n.events[ev].targets;
    } else if (field === "lead") n.events[ev].lead = parseInt(value, 10) || 0;
    else n.events[ev][field] = value;
    this._markDirty(false);
    void isChange;
  }

  async _onClick(e) {
    const t = e.target.closest("[data-tab],[data-act]");
    if (!t) return;
    if (t.dataset.tab) { this._tab = t.dataset.tab; this._render(); return; }
    if (e.target.closest("label.sw")) return;     // the enable checkbox inside a slot header
    const act = t.dataset.act;
    const svc = (s, data) => this._hass.callService(DOMAIN, s, { ...(this._cfg.entry_id ? { config_entry_id: this._cfg.entry_id } : {}), ...data });
    const real = () => !(this.data.flags || {}).dry_run;
    try {
      if (act === "toggle") { const i = +t.dataset.i; this._open.has(i) ? this._open.delete(i) : this._open.add(i); this._render(); }
      else if (act === "addslot") {
        const ids = new Set(this.draft.slots.map((s) => s.id)); let n = this.draft.slots.length + 1; while (ids.has(`slot_${n}`)) n++;
        this.draft.slots.push({ id: `slot_${n}`, name: `Slot ${n}`, enabled: true, anchor: { mode: "start", ref: "time", at: "06:00" }, zones: [] });
        this._open.add(this.draft.slots.length - 1); this._markDirty(true);
      } else if (act === "delslot") {
        const i = +t.dataset.i; if (!confirm(`Delete slot "${this.draft.slots[i].name || this.draft.slots[i].id}"?`)) return;
        this.draft.slots.splice(i, 1); this._open.clear(); this._markDirty(true);
      } else if (act === "nopump") { this.draft.pump = {}; this._markDirty(true);
      } else if (act === "revert") { this.dirty = false; this.draft = this._makeDraft(this.data); this.preview = null; this._render(); }
      else if (act === "save") {
        try {
          this.data = await this._ws({ type: `${DOMAIN}/save`, config: this.draft });
          this._fetched = Date.now(); this.dirty = false; this.draft = this._makeDraft(this.data); this.preview = null; this._render();
        } catch (err) { this._saveErr = err.message || String(err); this._renderBar(); }
      } else if (act === "stop") { await svc("stop", {}); setTimeout(() => this._load(), 1500); }
      else if (act === "skip") { await svc("skip_next", {}); setTimeout(() => this._load(), 800); }
      else if (act === "runslot" || act === "runslot1") {
        if (this.dirty) { alert("Save the changes first."); return; }
        const slot = act === "runslot" ? this.shadowRoot.getElementById("runslot").value : t.dataset.slot;
        if (real() && !confirm("Dry run is OFF - this will really water. Start now?")) return;
        await svc("run_slot", { slot }); setTimeout(() => this._load(), 2500);
      } else if (act === "runzone") {
        const m = num(this.shadowRoot.getElementById(`rz-${t.dataset.zone}`).value);
        if (!m) return;
        if (real() && !confirm(`Dry run is OFF - this will really water for ${m} min. Start now?`)) return;
        await svc("run_zone", { zone: t.dataset.zone, minutes: m }); setTimeout(() => this._load(), 2500);
      } else if (act === "testnotif") {
        if (this.dirty) { alert("Save the changes first."); return; }
        await svc("test_notification", { event: t.dataset.ev });
      }
    } catch (err) { alert(err.message || String(err)); }
  }

  _moveNow() {
    if (!this.data) return;
    const now = this._nowIso();
    for (const el of this.shadowRoot.querySelectorAll(".mark.now")) el.style.left = `${(now.min / 14.4).toFixed(3)}%`;
  }
}

const CSS = `
:host { display:block; }
ha-card { overflow:hidden; }
.wrap { padding:12px 14px 0; font-size:14px; color:var(--primary-text-color,#1c1c1c); }
.pad { padding:12px 0; }
.head { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.title { font-size:18px; font-weight:600; margin-right:auto; }
.chip { font-size:11px; font-weight:600; padding:2px 8px; border-radius:10px; background:var(--secondary-background-color,#eee); color:var(--primary-text-color,#333); }
.chip.small { font-size:10px; padding:1px 6px; margin-left:4px; }
.chip.warn { background:#f5a52433; color:#a86400; }
.chip.off, .st-disabled { background:#8883; }
.st-running { background:#2fbf7133; color:#147a44; }
.st-dry_run, .st-scheduled { background:#4e9cf533; color:#1d5fae; }
.st-error { background:#e5484d33; color:#b3261e; }
.banner { margin:8px 0; padding:6px 10px; border-radius:8px; }
.err { color:#b3261e; } .banner.err { background:#e5484d1a; }
.tabs { display:flex; gap:2px; margin:10px 0 6px; border-bottom:1px solid var(--divider-color,#ddd); overflow-x:auto; }
.tab { background:none; border:0; padding:8px 12px; cursor:pointer; color:var(--secondary-text-color,#666); font:inherit; border-bottom:2px solid transparent; }
.tab.on { color:var(--primary-color,#03a9f4); border-bottom-color:var(--primary-color,#03a9f4); font-weight:600; }
.body { padding-bottom:10px; }
.lbl { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--secondary-text-color,#777); margin:12px 0 6px; }
.muted { color:var(--secondary-text-color,#777); } .small { font-size:12px; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.box { background:var(--secondary-background-color,#f4f4f4); border-radius:10px; padding:8px 10px; }
.big { font-size:17px; font-weight:600; display:flex; align-items:center; gap:6px; }
.actions, .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:8px 0; }
.grow { flex:1; }
button, select, input { font:inherit; font-size:13px; }
button { border:1px solid var(--divider-color,#ccc); background:var(--card-background-color,#fff); color:var(--primary-text-color,#222); border-radius:8px; padding:5px 10px; cursor:pointer; }
button.primary { background:var(--primary-color,#03a9f4); color:#fff; border-color:transparent; }
button.danger { color:#b3261e; border-color:#e5484d66; }
input, select { border:1px solid var(--divider-color,#ccc); border-radius:6px; padding:3px 6px; background:var(--card-background-color,#fff); color:var(--primary-text-color,#222); }
input.n { width:64px; } input.name { width:180px; } input[type=color] { width:34px; height:26px; padding:1px; }
label.wide { flex:1; display:flex; gap:6px; align-items:center; } label.wide input { flex:1; }
.dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; flex:none; }
.tl { position:relative; height:46px; background:var(--secondary-background-color,#f2f2f2); border-radius:8px; margin-bottom:16px; }
.tl.compact { height:20px; margin-bottom:0; border-radius:5px; }
.run { position:absolute; top:6px; bottom:6px; display:flex; border-radius:4px; overflow:hidden; box-shadow:0 0 0 1px #0002; cursor:default; }
.tl.compact .run { top:3px; bottom:3px; }
.run i { display:block; min-width:1px; } .run.merged { box-shadow:0 0 0 2px var(--primary-color,#03a9f4); } .run.skipped { opacity:.3; }
.mark { position:absolute; top:0; bottom:0; width:2px; } .mark.sunrise { background:#f5a524aa; } .mark.sunset { background:#a970ffaa; } .mark.now { background:#e5484d; z-index:2; }
.ticks { position:absolute; left:0; right:0; bottom:-15px; height:14px; font-size:10px; color:var(--secondary-text-color,#888); }
.ticks span { position:absolute; transform:translateX(-2px); }
.wrow { display:flex; align-items:center; gap:8px; margin:4px 0; } .wday { width:66px; font-size:12px; flex:none; } .wtl { flex:1; } .wsum { font-size:11px; color:var(--secondary-text-color,#888); margin-top:1px; }
.legend { display:flex; gap:10px; flex-wrap:wrap; margin:8px 0; font-size:12px; } .legend i { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:4px; }
.list { list-style:none; padding:0; margin:4px 0; } .list li.past { opacity:.45; } .list li { padding:6px 0; border-bottom:1px solid var(--divider-color,#eee); } .note { font-size:12px; color:#a86400; }
.zl .zrow { display:flex; align-items:center; gap:4px; flex-wrap:wrap; padding:5px 0; border-bottom:1px solid var(--divider-color,#eee); } .zrow b { margin-right:6px; } .zrow.on b { color:#147a44; }
.dis { opacity:.55; }
.slot { border:1px solid var(--divider-color,#ddd); border-radius:10px; margin:6px 0; }
.shead { display:flex; align-items:center; gap:8px; padding:8px 10px; cursor:pointer; flex-wrap:wrap; } .caret { width:12px; }
.sbody { padding:0 10px 8px; border-top:1px solid var(--divider-color,#eee); }
label.day { display:inline-flex; align-items:center; gap:2px; font-size:12px; }
.zt { border-collapse:collapse; width:100%; margin:6px 0; } .zt td, .zt th { padding:3px 4px; text-align:left; border-bottom:1px solid var(--divider-color,#eee); font-weight:normal; } .zt th { font-size:11px; color:var(--secondary-text-color,#888); }
.zbox { border:1px solid var(--divider-color,#ddd); border-radius:10px; padding:4px 10px; margin:6px 0; }
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
.chart { display:flex; gap:3px; height:130px; align-items:stretch; margin:6px 0 2px; }
.cc { flex:1; display:flex; flex-direction:column; align-items:center; font-size:10px; color:var(--secondary-text-color,#888); position:relative; }
.cc.today span { color:var(--primary-color,#03a9f4); font-weight:700; }
.stack { flex:1; width:72%; display:flex; flex-direction:column-reverse; border-bottom:1px solid var(--divider-color,#ccc); }
.stack i { display:block; width:100%; }
.cc em { font-style:normal; height:13px; } .cc span { margin-top:2px; }
details.runs { margin-top:8px; } details.runs summary { cursor:pointer; color:var(--secondary-text-color,#777); font-size:12px; font-weight:600; }
.svcs { display:flex; flex-wrap:wrap; gap:6px; margin:4px 0 8px; }
.svc { border:1px solid var(--divider-color,#ccc); border-radius:14px; padding:2px 10px 2px 4px; display:inline-flex; align-items:center; gap:4px; cursor:pointer; font-size:12px; }
.svc.on { border-color:var(--primary-color,#03a9f4); background:color-mix(in srgb, var(--primary-color,#03a9f4) 12%, transparent); }
input.picker { width:320px; } input.bad { border-color:#e5484d; }
.bar { position:sticky; bottom:0; display:none; gap:8px; align-items:center; padding:8px 14px; margin:0 -14px; background:var(--card-background-color,#fff); border-top:1px solid var(--divider-color,#ddd); }
.bar.show { display:flex; }
@media (max-width:520px) { .grid2 { grid-template-columns:1fr; } }
`;

customElements.define("esp-sprinkler-planner-card", EspSprinklerPlannerCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "esp-sprinkler-planner-card", name: "ESP Sprinkler Planner", description: "Plan, run and edit ESP sprinkler schedules." });
