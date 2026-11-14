"""Sensors: next run, status."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from . import model
from .const import DOMAIN

STATUSES = ["idle", "scheduled", "running", "dry_run", "disabled", "error", "offline"]


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
                "last_event": self.rt.last_event, "error": self.rt.error,
                "offline_since": self.rt.health["since"],
                "missing_entities": self.rt.health["missing"], "unavailable_entities": self.rt.health["unavailable"]}


class ActiveZone(_Base, SensorEntity):
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, entry):
        super().__init__(entry, "active_zone", "Active zone")

    @property
    def native_value(self):
        z = self.rt.active_zone
        return z["name"] if z else "none"

    @property
    def extra_state_attributes(self):
        return dict(self.rt.active_zone or {})


class _ZoneBase(_Base):
    def __init__(self, entry, valve, key, label):
        self.zid = valve["id"]
        super().__init__(entry, f"{self.zid}_{key}", f"{valve.get('name') or self.zid} {label}")


class ZoneNext(_ZoneBase, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, entry, valve):
        super().__init__(entry, valve, "next_run", "next run")

    @property
    def native_value(self):
        start, _m = self.rt.zone_next(self.zid)
        return dt_util.as_utc(start) if start else None

    @property
    def extra_state_attributes(self):
        _s, minutes = self.rt.zone_next(self.zid)
        return {"minutes": minutes, "zone": self.zid}


class ZoneLast(_ZoneBase, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:history"

    def __init__(self, entry, valve):
        super().__init__(entry, valve, "last_run", "last run")

    @property
    def native_value(self):
        last = self.rt.last_run.get(self.zid)
        return dt_util.parse_datetime(last["end"]) if last else None

    @property
    def extra_state_attributes(self):
        last = self.rt.last_run.get(self.zid) or {}
        return {"minutes": last.get("minutes"), "started": last.get("start"), "zone": self.zid}


class ZoneToday(_ZoneBase, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "min"
    _attr_icon = "mdi:timer-sand"

    def __init__(self, entry, valve):
        super().__init__(entry, valve, "minutes_today", "minutes today")

    @property
    def native_value(self):
        return round(self.rt.minutes_today(self.zid), 1)

    @property
    def extra_state_attributes(self):
        days = sorted(self.rt.history)[-7:]
        return {"last_7_days": {d: self.rt.history[d].get(self.zid, 0) for d in days}, "zone": self.zid}


async def async_setup_entry(hass, entry, async_add_entities):
    ents = [NextRun(entry), Status(entry), ActiveZone(entry)]
    for v in entry.runtime_data.valves:
        ents += [ZoneNext(entry, v), ZoneLast(entry, v), ZoneToday(entry, v)]
    async_add_entities(ents)
