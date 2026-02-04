"""
Constants for the Swiss Electricity Tariffs (ElCom/LINDAS) custom integration.
Language: English in code/comments. Swiss spelling in README/translations.
"""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "swiss_electricity_tariffs"
NAME = "Swiss Electricity Tariffs (ElCom/LINDAS)"
PLATFORMS = ["sensor"]

CONF_MUNICIPALITY_TEXT = "municipality_text"  # free-text search term
CONF_MUNICIPALITY_URI = "municipality_uri"
CONF_MUNICIPALITY_LABEL = "municipality_label"
CONF_YEAR = "year"
CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"

DEFAULT_SCAN_INTERVAL = timedelta(days=1)  # 86400s
DEFAULT_UPDATE_INTERVAL_HOURS = 24

API_ENDPOINT = "https://lindas.admin.ch/query"
NAMED_GRAPH = "https://lindas.admin.ch/elcom/electricityprice"

# Keys for normalized data in the coordinator
DATA_TOTAL = "total"
DATA_ENERGY = "energy"
DATA_GRID = "grid"
DATA_FEES = "fees"
DATA_METERING = "metering"
DATA_UNITS = "units"  # dict mapping component -> unit
DATA_META = "meta"  # metadata like timestamps, raw obs ids, etc.

# Sensor key -> friendly label suffix
SENSOR_SPECS = {
    DATA_TOTAL: "Total Price",
    DATA_ENERGY: "Energy Price",
    DATA_GRID: "Grid Price",
    DATA_FEES: "Fees Price",
    DATA_METERING: "Metering Price",
}

ATTR_SOURCE = "source"
ATTR_LAST_UPDATE = "last_update"
ATTR_RAW_OBS_IDS = "raw_observation_ids"
ATTR_MUNICIPALITY_LABEL = "municipality_label"
ATTR_MUNICIPALITY_URI = "municipality_uri"
ATTR_YEAR = "year"

SOURCE_NAME = "ElCom/LINDAS"

# Discovery heuristics
MUNICIPALITY_PRED_HINTS = ("municip", "gemeinde", "commune", "gemeindeid")
YEAR_PRED_HINTS = ("year", "jahr")

COMPONENT_KEYWORDS = (
    "total",
    "price",
    "tarif",
    "energy",
    "grid",
    "netz",
    "fee",
    "abgabe",
    "meter",
    "base",
    "unit",
    "chf",
    "kwh",
    "month",
)
