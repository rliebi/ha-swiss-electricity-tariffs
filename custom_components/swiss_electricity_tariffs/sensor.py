"""
Sensor platform for Swiss Electricity Tariffs.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    NAME,
    SENSOR_SPECS,
    DATA_META,
    DATA_UNITS,
    ATTR_SOURCE,
    ATTR_LAST_UPDATE,
    ATTR_RAW_OBS_IDS,
    ATTR_MUNICIPALITY_LABEL,
    ATTR_MUNICIPALITY_URI,
    ATTR_YEAR,
)
from .coordinator import SwissTariffCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: SwissTariffCoordinator = data["coordinator"]

    entities = []
    for key, label_suffix in SENSOR_SPECS.items():
        entities.append(TariffSensorEntity(coordinator, entry, key, label_suffix))

    async_add_entities(entities)


class TariffSensorEntity(CoordinatorEntity[SwissTariffCoordinator], SensorEntity):
    def __init__(self, coordinator: SwissTariffCoordinator, entry: ConfigEntry, key: str, label_suffix: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._label_suffix = label_suffix
        # Use initial data for unique_id stability; prefer municipality_uri only
        uri = entry.data.get(ATTR_MUNICIPALITY_URI) or entry.data.get("municipality_uri")
        self._attr_unique_id = f"{uri}|{key}"

    @property
    def name(self) -> str | None:
        meta = (self.coordinator.data or {}).get(DATA_META, {})
        muni_label = meta.get("municipality_label")
        name_prefix = f"Swiss Tariff {muni_label}" if muni_label else NAME
        return f"{name_prefix} {self._label_suffix}"

    @property
    def native_value(self) -> Optional[float]:
        data = self.coordinator.data or {}
        return data.get(self._key)

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        data = self.coordinator.data or {}
        units = data.get(DATA_UNITS, {})
        return units.get(self._key)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        data = self.coordinator.data or {}
        meta = data.get(DATA_META, {})
        attrs = {
            ATTR_MUNICIPALITY_LABEL: meta.get("municipality_label"),
            ATTR_MUNICIPALITY_URI: meta.get("municipality_uri"),
            ATTR_YEAR: meta.get("year"),
            ATTR_SOURCE: meta.get("source"),
            ATTR_LAST_UPDATE: meta.get("last_update"),
        }
        raw_ids = meta.get("raw_observation_ids")
        if raw_ids:
            attrs[ATTR_RAW_OBS_IDS] = raw_ids
        return attrs

    @property
    def available(self) -> bool:
        # Available if coordinator OK and we have at least some data field
        return super().available and (self.coordinator.data is not None)
