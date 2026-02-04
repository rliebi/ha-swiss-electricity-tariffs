"""
Config flow for Swiss Electricity Tariffs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_MUNICIPALITY_TEXT,
    CONF_MUNICIPALITY_URI,
    CONF_MUNICIPALITY_LABEL,
    CONF_YEAR,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
)
from .api import LindaSparqlClient

_LOGGER = logging.getLogger(__name__)


class SwissTariffsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Swiss Electricity Tariffs."""

    VERSION = 1

    def __init__(self) -> None:
        self._search_text: Optional[str] = None
        self._search_results: List[Tuple[str, str]] = []
        self._selected_muni: Optional[Tuple[str, str]] = None

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """First step: ask for municipality search text and perform lookup."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            text = str(user_input.get(CONF_MUNICIPALITY_TEXT, "")).strip()
            if not text:
                errors[CONF_MUNICIPALITY_TEXT] = "required"
            else:
                self._search_text = text
                # Perform async search
                try:
                    session = async_get_clientsession(self.hass)
                    client = LindaSparqlClient(session)
                    self._search_results = await client.search_municipalities(text, limit=10)
                    if not self._search_results:
                        errors[CONF_MUNICIPALITY_TEXT] = "no_results"
                    else:
                        return await self.async_step_select_municipality()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Search failed: %s", err)
                    errors["base"] = "cannot_connect"

        data_schema = self._schema_text()
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    def _schema_text(self):
        import voluptuous as vol

        return vol.Schema({vol.Required(CONF_MUNICIPALITY_TEXT): str})

    async def async_step_select_municipality(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Second step: show dropdown of search results and ask for year."""
        import voluptuous as vol

        errors: Dict[str, str] = {}
        current_year = datetime.now().year

        choices = {label: uri for uri, label in self._search_results}
        if user_input is not None:
            label = user_input.get(CONF_MUNICIPALITY_LABEL)
            year = int(user_input.get(CONF_YEAR, current_year))
            if label not in choices:
                errors[CONF_MUNICIPALITY_LABEL] = "invalid_choice"
            else:
                uri = choices[label]
                self._selected_muni = (uri, label)
                unique_id = f"{uri}|{year}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                data = {
                    CONF_MUNICIPALITY_URI: uri,
                    CONF_MUNICIPALITY_LABEL: label,
                    CONF_YEAR: year,
                }
                return self.async_create_entry(title=label, data=data)

        default_label = self._search_results[0][1] if self._search_results else ""
        schema = vol.Schema(
            {
                vol.Required(CONF_MUNICIPALITY_LABEL, default=default_label): vol.In(list(choices.keys())),
                vol.Required(CONF_YEAR, default=current_year): int,
            }
        )
        return self.async_show_form(step_id="select_municipality", data_schema=schema, errors=errors)

    @staticmethod
    def _opt_schema(current: Dict[str, Any], muni_choices: Optional[List[Tuple[str, str]]] = None):
        import voluptuous as vol

        schema_dict: Dict[Any, Any] = {
            vol.Required(CONF_YEAR, default=current.get(CONF_YEAR, datetime.now().year)): int,
            vol.Required(CONF_UPDATE_INTERVAL_HOURS, default=current.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS)): int,
        }
        if muni_choices:
            labels = [label for _, label in muni_choices]
            default_label = current.get(CONF_MUNICIPALITY_LABEL, labels[0] if labels else "")
            schema_dict[vol.Required(CONF_MUNICIPALITY_LABEL, default=default_label)] = vol.In(labels)
        return vol.Schema(schema_dict)

    async def async_step_options(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        return await self.async_step_init(user_input)

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Options flow first step: allow search or keep current municipality, year, interval."""
        errors: Dict[str, str] = {}
        if user_input is not None and "do_search" in user_input:
            # Start a search similar to setup flow
            try:
                text = str(user_input.get("do_search", "")).strip()
                session = async_get_clientsession(self.hass)
                client = LindaSparqlClient(session)
                self._search_results = await client.search_municipalities(text, limit=10)
                if not self._search_results:
                    errors["base"] = "no_results"
                else:
                    return await self.async_step_options_select()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Options search failed: %s", err)
                errors["base"] = "cannot_connect"

        # Show simple form to change year/interval or trigger search
        import voluptuous as vol

        schema = vol.Schema(
            {
                vol.Optional("do_search"): str,
                vol.Required(CONF_YEAR, default=self.config_entry.options.get(CONF_YEAR, self.config_entry.data.get(CONF_YEAR, datetime.now().year))): int,
                vol.Required(CONF_UPDATE_INTERVAL_HOURS, default=self.config_entry.options.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS)): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def async_step_options_select(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Finalize options, including municipality selection if search was done."""
        errors: Dict[str, str] = {}
        import voluptuous as vol

        choices = {label: uri for uri, label in self._search_results}
        if user_input is not None:
            label = user_input.get(CONF_MUNICIPALITY_LABEL)
            year = int(user_input.get(CONF_YEAR, self.config_entry.options.get(CONF_YEAR, datetime.now().year)))
            hours = int(user_input.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS))
            if label not in choices:
                errors[CONF_MUNICIPALITY_LABEL] = "invalid_choice"
            else:
                options = {
                    CONF_MUNICIPALITY_URI: choices[label],
                    CONF_MUNICIPALITY_LABEL: label,
                    CONF_YEAR: year,
                    CONF_UPDATE_INTERVAL_HOURS: max(1, hours),
                }
                return self.async_create_entry(title="Options", data=options)

        default_label = self._search_results[0][1] if self._search_results else self.config_entry.data.get(CONF_MUNICIPALITY_LABEL, "")
        schema = vol.Schema(
            {
                vol.Required(CONF_MUNICIPALITY_LABEL, default=default_label): vol.In(list(choices.keys() or [default_label])),
                vol.Required(CONF_YEAR, default=self.config_entry.options.get(CONF_YEAR, self.config_entry.data.get(CONF_YEAR, datetime.now().year))): int,
                vol.Required(CONF_UPDATE_INTERVAL_HOURS, default=self.config_entry.options.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS)): int,
            }
        )
        return self.async_show_form(step_id="options_select", data_schema=schema, errors=errors)


class SwissTariffsOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        flow = SwissTariffsConfigFlow()
        flow.hass = self.hass  # type: ignore[attr-defined]
        flow.config_entry = self.config_entry  # type: ignore[attr-defined]
        return await flow.async_step_init(user_input)


async def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
    return SwissTariffsOptionsFlowHandler(config_entry)
