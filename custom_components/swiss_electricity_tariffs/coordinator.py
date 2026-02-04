"""
DataUpdateCoordinator for Swiss Electricity Tariffs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN,
    CONF_MUNICIPALITY_LABEL,
    CONF_MUNICIPALITY_URI,
    CONF_YEAR,
    DATA_ENERGY,
    DATA_FEES,
    DATA_GRID,
    DATA_META,
    DATA_METERING,
    DATA_TOTAL,
    DATA_UNITS,
    SOURCE_NAME,
)
from .api import LindaSparqlClient

_LOGGER = logging.getLogger(__name__)


class SwissTariffCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator that fetches and normalizes tariff data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, update_hours: int) -> None:
        self.entry = entry
        self._update_hours = max(1, int(update_hours or 24))
        name = f"{DOMAIN}-{entry.entry_id}"
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=self._update_hours),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API and return normalized dict."""
        # Options override initial data if provided
        muni_label = self.entry.options.get(CONF_MUNICIPALITY_LABEL, self.entry.data.get(CONF_MUNICIPALITY_LABEL))
        muni_uri = self.entry.options.get(CONF_MUNICIPALITY_URI, self.entry.data.get(CONF_MUNICIPALITY_URI))
        year = int(self.entry.options.get(CONF_YEAR, self.entry.data.get(CONF_YEAR)))

        session = async_get_clientsession(self.hass)
        client = LindaSparqlClient(session)
        try:
            preds = await client.discover_model()
            bindings = await client.fetch_observations(muni_uri, year, preds)
            comp_values, units, raw_ids, meta = client.parse_components(bindings)
        except Exception as err:  # noqa: BLE001 - propagate as UpdateFailed
            raise UpdateFailed(str(err)) from err

        now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        data: Dict[str, Any] = {
            DATA_TOTAL: comp_values.get("total"),
            DATA_ENERGY: comp_values.get("energy"),
            DATA_GRID: comp_values.get("grid"),
            DATA_FEES: comp_values.get("fees"),
            DATA_METERING: comp_values.get("metering"),
            DATA_UNITS: units,
            DATA_META: {
                "municipality_label": muni_label,
                "municipality_uri": muni_uri,
                "year": year,
                "source": SOURCE_NAME,
                "last_update": now_iso,
                "raw_observation_ids": raw_ids,
            },
        }
        _LOGGER.debug("Coordinator normalized data: keys=%s", list(data.keys()))
        return data
