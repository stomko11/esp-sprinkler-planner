"""The ESPHome device behind a planner: its entities, in the order the ESP itself defines them.

The ESP runs its valves in the order of its YAML. Home Assistant's entity registry keeps entities in
the order they were first seen, so a valve added later in the middle of the YAML sits at the end
there. The ESPHome integration, however, keeps the entity list exactly as the device sends it, which
is the YAML order. That list is read here (it is internal to the ESPHome integration, so every step is
guarded); when it cannot be read, the registry order is used as before.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .discovery import Entity

_LOGGER = logging.getLogger(__name__)

_DOMAINS = {"SwitchInfo": "switch", "NumberInfo": "number"}


def esp_order(hass: HomeAssistant, device_id: str) -> Optional[Dict[str, int]]:
    """entity_id -> position in the ESP's own entity list, for its switches and numbers. None if unknown."""
    try:
        dev = dr.async_get(hass).async_get(device_id)
        if dev is None:
            return None
        entry = next((e for e in hass.config_entries.async_entries("esphome") if e.entry_id in dev.config_entries), None)
        data = getattr(entry, "runtime_data", None) if entry else None
        info = getattr(data, "info", None)
        if not info:
            return None
        reg = er.async_get(hass)
        ents = [e for e in er.async_entries_for_device(reg, device_id) if e.platform == "esphome"]
        by_uid = {(e.domain, e.unique_id): e.entity_id for e in ents}
        by_name = {(e.domain, e.original_name): e.entity_id for e in ents if e.original_name}
        try:
            from aioesphomeapi import build_device_unique_id  # type: ignore[attr-defined]
        except ImportError:   # older ESPHome library
            build_device_unique_id = None
        mac = entry.unique_id
        out: Dict[str, int] = {}
        pos = 0
        for info_type, infos in info.items():
            domain = _DOMAINS.get(getattr(info_type, "__name__", ""))
            if not domain:
                continue
            for item in infos.values():
                eid = None
                if build_device_unique_id and mac:
                    try:
                        eid = by_uid.get((domain, build_device_unique_id(mac, item)))
                    except Exception:  # noqa: BLE001 - internal API, fall back to the name
                        eid = None
                eid = eid or by_name.get((domain, getattr(item, "name", None)))
                if eid and eid not in out:
                    out[eid] = pos
                pos += 1
        return out or None
    except Exception as err:  # noqa: BLE001 - never break the planner over the order
        _LOGGER.debug("ESP order not readable for %s: %s", device_id, err)
        return None


def device_entities(hass: HomeAssistant, device_id: str) -> Tuple[List[Entity], bool]:
    """The device's entities for discovery, in ESP order when it is known. Returns (entities, from_esp)."""
    reg = er.async_get(hass)
    ents = list(er.async_entries_for_device(reg, device_id))
    order = esp_order(hass, device_id)
    out = []
    for i, e in enumerate(ents):
        caps = e.capabilities or {}
        pos = i
        if order is not None:
            # entities the ESP list has keep its order; anything else goes after, in registry order
            pos = order[e.entity_id] if e.entity_id in order else 100000 + i
        out.append(Entity(e.entity_id, e.name or e.original_name or e.entity_id, max=caps.get("max"), order=pos))
    return out, order is not None
