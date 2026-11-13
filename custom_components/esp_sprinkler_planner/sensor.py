"""Sensors: next run, status."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from . import model
from .const import DOMAIN

STATUSES = ["idle", "scheduled", "running", "dry_run", "disabled", "error"]


def device_info(entry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=f"{entry.title} planner",
                      manufacturer="ESP Sprinkler Planner", model="Planner")


class _Base:
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry, key: str, name: str) -> None:
        self.rt = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.rt.add_listener(self.async_write_ha_state))


class NextRun(_Base, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, entry):
        super().__init__(entry, "next_run", "Next run")

    @property
    def native_value(self):
        r = self.rt.next_run
        return dt_util.as_utc(r.start) if r else None

    @property
    def extra_state_attributes(self):
        r = self.rt.next_run
        out = model.run_to_dict(r, self.rt.zone_names()) if r else {}
        out["conflicts"] = [c.message for c in (self.rt.plan.conflicts if self.rt.plan else [])]
        if self.rt.error:
            out["error"] = self.rt.error
        return out


class Status(_Base, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_icon = "mdi:sprinkler"

    def __init__(self, entry):
        super().__init__(entry, "status", "Status")

    @property
    def native_value(self):
        return self.rt.status

    @property
    def extra_state_attributes(self):
        a = self.rt.active or {}
        return {"active_run": a.get("run"), "dry_run_mode": self.rt.flags["dry_run"], "calls": a.get("calls"),
                "last_event": self.rt.last_event, "error": self.rt.error}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([NextRun(entry), Status(entry)])
