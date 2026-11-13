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
                    DOMAIN, OPT_RESTORE, OPT_WATCHDOG)
from .discovery import Entity, propose


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
            dev = dr.async_get(self.hass).async_get(device_id)
            dname = (dev.name_by_user or dev.name) if dev else ""
            ents = _device_entities(self.hass, device_id)
            self._switches = [e.entity_id for e in ents if e.domain == "switch"]
            self._numbers = [e.entity_id for e in ents if e.domain == "number"]
            if not self._switches:
                errors["base"] = "no_switches"
            else:
                self._proposal = propose(ents, dname or "")
                self._data = {CONF_DEVICE: device_id, CONF_NAME: user_input.get(CONF_NAME) or dname or "Sprinklers"}
                return await self.async_step_controller()
        schema = vol.Schema({
            vol.Required(CONF_DEVICE): selector.DeviceSelector({"filter": {"integration": "esphome"}}),
            vol.Optional(CONF_NAME): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_controller(self, user_input=None):
        if user_input is not None:
            self._data[CONF_CONTROLLER] = {k: user_input.get(k) for k in CONTROLLER_KEYS}
            self._data[CONF_VALVE_OVERLAP] = int(user_input.get(CONF_VALVE_OVERLAP) or 0)
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
        fields[vol.Optional(CONF_VALVE_OVERLAP, default=0)] = selector.NumberSelector(
            {"min": 0, "max": 600, "step": 1, "unit_of_measurement": "s", "mode": "box"})
        return self.async_show_form(step_id="controller", data_schema=vol.Schema(fields))

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
                        "id": f"zone_{len(self._valves) + 1}",
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
            vol.Required("enabled", default=True): bool,
            vol.Required("skip", default=False): bool,
            vol.Required("add_another", default=False): bool,
        })
        return self.async_show_form(step_id="valve", data_schema=schema, errors=errors, description_placeholders={
            "index": str(n), "total": str(max(len(props), n)), "detected": cur.name if cur else "-"})

    def _finish(self):
        if not self._valves:
            return self.async_abort(reason="no_valves")
        self._data[CONF_VALVES] = sorted(self._valves, key=lambda v: (v["order"], v["id"]))
        return self.async_create_entry(title=self._data[CONF_NAME], data=self._data,
                                       options={OPT_RESTORE: True, OPT_WATCHDOG: DEFAULT_WATCHDOG})


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
