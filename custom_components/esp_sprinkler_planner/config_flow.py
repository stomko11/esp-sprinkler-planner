"""Config flow: pick the ESPHome device, confirm the controller entities, then one step per valve."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (CONF_CONTROLLER, CONF_DEVICE, CONF_VALVE_OVERLAP, CONF_VALVES, CONTROLLER_KEYS, DEFAULT_WATCHDOG,
                    DOMAIN, OPT_IMPORT, OPT_IMPORT_NOTES, OPT_RESTORE, OPT_WATCHDOG)
from . import backup as backup_mod
from . import model
from .discovery import Entity, ValveProposal, new_valves, propose


def _device_entities(hass, device_id: str) -> List[Entity]:
    reg = er.async_get(hass)
    out = []
    for i, e in enumerate(er.async_entries_for_device(reg, device_id)):
        caps = e.capabilities or {}
        out.append(Entity(e.entity_id, e.name or e.original_name or e.entity_id, max=caps.get("max"), order=i))
    return out


def _entity_selector(domain: str, include: List[str]) -> selector.EntitySelector:
    cfg: Dict[str, Any] = {"filter": {"domain": domain}}
    if include:
        cfg["include_entities"] = include
    return selector.EntitySelector(cfg)


def _suggested(value):
    return {"suggested_value": value} if value else None


CONF_BACKUP = "backup"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._proposal = None
        self._switches: List[str] = []
        self._numbers: List[str] = []
        self._idx = 0
        self._extra = False
        self._valves: List[Dict[str, Any]] = []
        self._backup: Optional[Dict[str, Any]] = None   # settings backup chosen in the first step
        self._reconf = None          # config entry being reconfigured

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            device_id = user_input[CONF_DEVICE]
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()
            self._backup = None
            if user_input.get(CONF_BACKUP):
                try:
                    self._backup = await self._read_backup(user_input[CONF_BACKUP])
                except backup_mod.BackupError as err:
                    errors[CONF_BACKUP] = "invalid_backup"
                    self._backup_error = str(err)
            dev = dr.async_get(self.hass).async_get(device_id)
            dname = (dev.name_by_user or dev.name) if dev else ""
            ents = _device_entities(self.hass, device_id)
            self._switches = [e.entity_id for e in ents if e.domain == "switch"]
            self._numbers = [e.entity_id for e in ents if e.domain == "number"]
            if errors:
                pass
            elif not self._switches:
                errors["base"] = "no_switches"
            else:
                self._proposal = propose(ents, dname or "")
                self._data = {CONF_DEVICE: device_id, CONF_NAME: user_input.get(CONF_NAME) or dname or "Sprinklers"}
                return await self.async_step_controller()
        schema = vol.Schema({
            vol.Required(CONF_DEVICE): selector.DeviceSelector({"filter": {"integration": "esphome"}}),
            vol.Optional(CONF_NAME): str,
            vol.Optional(CONF_BACKUP): selector.FileSelector(selector.FileSelectorConfig(accept=".json,application/json")),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors, description_placeholders={
            "backup_error": getattr(self, "_backup_error", "") if errors.get(CONF_BACKUP) else ""})

    async def _read_backup(self, file_id: str) -> Dict[str, Any]:
        from homeassistant.components.file_upload import process_uploaded_file

        def read() -> str:
            with process_uploaded_file(self.hass, file_id) as path:
                return path.read_text(encoding="utf-8", errors="replace")
        try:
            text = await self.hass.async_add_executor_job(read)
        except (OSError, ValueError) as err:
            raise backup_mod.BackupError("the file could not be read") from err
        return backup_mod.parse(text)

    async def async_step_reconfigure(self, user_input=None):
        """Change the mapping of an existing planner: same steps, pre-filled with the current values.
        Zone ids stay the same, so slots, settings and history are kept."""
        entry = self._get_reconfigure_entry()
        self._reconf = entry
        device_id = entry.data[CONF_DEVICE]
        ents = _device_entities(self.hass, device_id)
        self._switches = [e.entity_id for e in ents if e.domain == "switch"]
        self._numbers = [e.entity_id for e in ents if e.domain == "number"]
        dev = dr.async_get(self.hass).async_get(device_id)
        self._proposal = propose(ents, (dev.name_by_user or dev.name) if dev else "")
        self._proposal.controller = dict(entry.data.get(CONF_CONTROLLER) or {})
        saved = list(entry.data.get(CONF_VALVES) or [])
        found = self._proposal.valves
        pos = {f.duration: f.order for f in found if f.duration}     # position on the ESP now
        rows = [(ValveProposal(v.get("name") or v["id"], v.get("valve_switch"), v.get("enable_switch"),
                               v.get("duration"), v.get("max_minutes"), pos.get(v.get("duration"), int(v.get("order", i)))),
                 v["id"], v.get("enabled", True)) for i, v in enumerate(saved)]
        fresh = new_valves([r[0] for r in rows], found)
        rows += [(v, None, True) for v in fresh]      # valves added on the ESP since: offered as new zones
        rows.sort(key=lambda r: r[0].order)           # stable: a saved zone stays ahead of a new one with the same position
        self._proposal.valves = [r[0] for r in rows]
        self._ids = [r[1] for r in rows]              # per proposal: the zone id it keeps, None = new zone
        self._all_ids = [v["id"] for v in saved]
        self._enabled = [r[2] for r in rows]
        self._new_names = [r[0].name for r in rows if r[1] is None]
        self._data = {k: entry.data[k] for k in entry.data}
        return await self.async_step_controller()

    async def async_step_controller(self, user_input=None):
        if user_input is not None:
            self._data[CONF_CONTROLLER] = {k: user_input.get(k) for k in CONTROLLER_KEYS}
            self._data[CONF_VALVE_OVERLAP] = int(user_input.get(CONF_VALVE_OVERLAP) or 0)
            if any(v.enable_switch and v.duration for v in self._proposal.valves):
                return await self.async_step_zones()
            return await self.async_step_valve()
        fields: Dict[Any, Any] = {}
        for key in CONTROLLER_KEYS:
            is_num = key in ("multiplier", "repeat")
            sel = _entity_selector("number" if is_num else "switch", self._numbers if is_num else self._switches)
            proposed = self._proposal.controller.get(key)
            if key == "main_switch":
                fields[vol.Required(key, description=_suggested(proposed))] = sel
            else:
                fields[vol.Optional(key, description=_suggested(proposed))] = sel
        overlap = int((self._reconf.options.get(CONF_VALVE_OVERLAP, self._reconf.data.get(CONF_VALVE_OVERLAP, 0))
                       if self._reconf else ((self._backup or {}).get("entry") or {}).get("valve_overlap", 0)) or 0)
        fields[vol.Optional(CONF_VALVE_OVERLAP, default=overlap)] = selector.NumberSelector(
            {"min": 0, "max": 600, "step": 1, "unit_of_measurement": "s", "mode": "box"})
        return self.async_show_form(step_id="controller", data_schema=vol.Schema(fields))

    async def async_step_zones(self, user_input=None):
        """All detected zones at once: take them as they are, or go through them one by one."""
        props = self._proposal.valves
        complete = [v for v in props if v.enable_switch and v.duration]
        if user_input is not None:
            if user_input.get("check_each"):
                return await self.async_step_valve()
            for i, v in enumerate(props):
                if not (v.enable_switch and v.duration):
                    continue
                self._idx = i
                self._valves.append({
                    "id": self._zone_id({"name": v.name, "duration": v.duration, "enable_switch": v.enable_switch,
                                         "valve_switch": v.valve_switch}), "name": v.name, "order": v.order,
                    "enabled": self._enabled[i] if self._reconf and i < len(self._enabled) else True,
                    "valve_switch": v.valve_switch, "enable_switch": v.enable_switch, "duration": v.duration,
                    "max_minutes": v.max_minutes,
                })
            self._idx = len(props)
            if user_input.get("add_more"):
                self._extra = True
                return await self.async_step_valve()
            return self._finish()
        lines = []
        for v in props:
            ok = v.enable_switch and v.duration
            lines.append(f"{v.order + 1}. **{v.name}**" + ("" if ok else " - incomplete, check it one by one")
                         + ("" if v.valve_switch or not ok else " (no valve switch: status from the controller only)"))
        schema = vol.Schema({
            vol.Required("check_each", default=len(complete) < len(props)): bool,
            vol.Required("add_more", default=False): bool,
        })
        new = getattr(self, "_new_names", []) if self._reconf else []
        return self.async_show_form(step_id="zones", data_schema=schema, description_placeholders={
            "count": str(len(complete)), "zones": "\n".join(lines),
            "new": ("**New on the device:** " + ", ".join(new) + "\n\n") if new else ""})

    async def async_step_valve(self, user_input=None):
        props = self._proposal.valves
        cur = props[self._idx] if self._idx < len(props) else None
        errors = {}
        if user_input is not None:
            if not user_input.get("skip"):
                if not user_input.get("enable_switch"):
                    errors["enable_switch"] = "required"
                if not user_input.get("duration"):
                    errors["duration"] = "required"
            if not errors:
                if not user_input.get("skip"):
                    max_m = cur.max_minutes if cur and user_input.get("duration") == cur.duration else None
                    if max_m is None:
                        st = self.hass.states.get(user_input["duration"])
                        max_m = st.attributes.get("max") if st else None
                    self._valves.append({
                        "id": self._zone_id({"name": user_input.get("name") or (cur.name if cur else ""),
                                             "duration": user_input.get("duration"),
                                             "enable_switch": user_input.get("enable_switch"),
                                             "valve_switch": user_input.get("valve_switch")}),
                        "name": user_input.get("name") or (cur.name if cur else f"Zone {len(self._valves) + 1}"),
                        "order": int(user_input.get("order", len(self._valves))),
                        "enabled": bool(user_input.get("enabled", True)),
                        "valve_switch": user_input.get("valve_switch"),
                        "enable_switch": user_input["enable_switch"],
                        "duration": user_input["duration"],
                        "max_minutes": max_m,
                    })
                self._idx += 1
                self._extra = bool(user_input.get("add_another"))
                if self._idx < len(props) or self._extra:
                    return await self.async_step_valve()
                return self._finish()
        n = self._idx + 1
        schema = vol.Schema({
            vol.Optional("name", description=_suggested(cur.name if cur else None)): str,
            vol.Optional("enable_switch", description=_suggested(cur.enable_switch if cur else None)):
                _entity_selector("switch", self._switches),
            vol.Optional("duration", description=_suggested(cur.duration if cur else None)):
                _entity_selector("number", self._numbers),
            vol.Optional("valve_switch", description=_suggested(cur.valve_switch if cur else None)):
                _entity_selector("switch", self._switches),
            vol.Required("order", default=cur.order if cur else self._idx): selector.NumberSelector(
                {"min": 0, "max": 63, "step": 1, "mode": "box"}),
            vol.Required("enabled", default=self._enabled[self._idx] if self._reconf and self._idx < len(self._enabled) else True): bool,
            vol.Required("skip", default=False): bool,
            vol.Required("add_another", default=False): bool,
        })
        return self.async_show_form(step_id="valve", data_schema=schema, errors=errors, description_placeholders={
            "index": str(n), "total": str(max(len(props), n)), "detected": cur.name if cur else "-"})

    def _zone_id(self, cand: Optional[Dict[str, Any]] = None) -> str:
        """Reconfigure: the valve keeps its zone id; a new valve gets the next free one.
        Added from a backup: a valve that is in the backup gets its saved id back."""
        if self._reconf and self._idx < len(getattr(self, "_ids", [])) and self._ids[self._idx]:
            return self._ids[self._idx]
        saved = (self._backup or {}).get("valves") or []
        if saved and cand:
            m = backup_mod.match_valve(cand, saved, [v["id"] for v in self._valves])
            if m:
                return m["id"]
        taken = {v["id"] for v in self._valves} | set(getattr(self, "_all_ids", [])) | {v["id"] for v in saved}
        n = 1
        while f"zone_{n}" in taken:
            n += 1
        return f"zone_{n}"

    def _finish(self):
        if not self._valves:
            return self.async_abort(reason="no_valves")
        self._data[CONF_VALVES] = sorted(self._valves, key=lambda v: (v["order"], v["id"]))
        if self._reconf:
            opts = {**self._reconf.options, CONF_VALVE_OVERLAP: self._data.get(CONF_VALVE_OVERLAP, 0)}
            self.hass.config_entries.async_update_entry(self._reconf, options=opts)
            return self.async_update_reload_and_abort(self._reconf, data=self._data, reason="reconfigured")
        options: Dict[str, Any] = {OPT_RESTORE: True, OPT_WATCHDOG: DEFAULT_WATCHDOG}
        if self._backup:
            wd = (self._backup.get("entry") or {}).get("watchdog_margin")
            if isinstance(wd, (int, float)) and 0 < wd <= 600:
                options[OPT_WATCHDOG] = wd
            saved = {v["id"]: v for v in self._backup["valves"]}
            for v in self._data[CONF_VALVES]:
                if v["id"] in saved:
                    v["enabled"] = saved[v["id"]].get("enabled", True)
            cfg, notes = backup_mod.prepare(self._backup, [v["id"] for v in self._data[CONF_VALVES]])
            try:
                model.parse(cfg, self._data[CONF_VALVES], int(self._data.get(CONF_VALVE_OVERLAP) or 0))
                options[OPT_IMPORT] = cfg
            except model.ConfigError as err:
                notes = [f"The settings in the backup could not be used and were not restored: {err}"]
            if notes:
                options[OPT_IMPORT_NOTES] = notes
        return self.async_create_entry(title=self._data[CONF_NAME], data=self._data, options=options)


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data={**user_input, CONF_VALVE_OVERLAP: int(user_input[CONF_VALVE_OVERLAP]),
                                                 OPT_WATCHDOG: int(user_input[OPT_WATCHDOG])})
        o = self.config_entry.options
        overlap = o.get(CONF_VALVE_OVERLAP, self.config_entry.data.get(CONF_VALVE_OVERLAP, 0))
        schema = vol.Schema({
            vol.Required(OPT_RESTORE, default=o.get(OPT_RESTORE, True)): bool,
            vol.Required(OPT_WATCHDOG, default=o.get(OPT_WATCHDOG, DEFAULT_WATCHDOG)): selector.NumberSelector(
                {"min": 1, "max": 240, "step": 1, "unit_of_measurement": "min", "mode": "box"}),
            vol.Required(CONF_VALVE_OVERLAP, default=overlap): selector.NumberSelector(
                {"min": 0, "max": 600, "step": 1, "unit_of_measurement": "s", "mode": "box"}),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
