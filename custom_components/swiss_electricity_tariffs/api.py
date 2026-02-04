"""
Async SPARQL client and tariff parsing for the Swiss Electricity Tariffs integration.

This module talks to the LINDAS SPARQL endpoint and implements a simple
model discovery to find predicates for municipality and year. It then pulls
observations and extracts meaningful price components using keyword matching.

Design goals:
- Fully async (aiohttp via HA client session)
- Robust to data-model variations using heuristics
- Conservative logging, no sensitive data
- Clear type hints
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from aiohttp import ClientSession, ClientError

from .const import (
    API_ENDPOINT,
    NAMED_GRAPH,
    MUNICIPALITY_PRED_HINTS,
    YEAR_PRED_HINTS,
    COMPONENT_KEYWORDS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    municipality_pred: str
    year_pred: str


class LindaSparqlClient:
    """Lightweight SPARQL client for LINDAS endpoint."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _post_query(self, query: str) -> Dict[str, Any]:
        headers = {
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/sparql-query; charset=UTF-8",
        }
        data = query.encode("utf-8")
        try:
            async with self._session.post(API_ENDPOINT, data=data, headers=headers, timeout=60) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"SPARQL HTTP {resp.status}: {text[:200]}")
                return await resp.json(content_type=None)
        except ClientError as err:
            raise RuntimeError(f"Network error talking to LINDAS: {err}") from err

    @staticmethod
    def _binding_value(bind: Dict[str, Any]) -> str:
        return bind.get("value", "")

    async def search_municipalities(self, search_text: str, limit: int = 10) -> List[Tuple[str, str]]:
        """Search municipalities by label/name.

        Returns list of tuples (uri, label).
        """
        search = search_text.replace("\"", " ")
        query = (
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
            "PREFIX schema: <http://schema.org/>\n"
            "SELECT DISTINCT ?muni ?label\n"
            f"FROM <{NAMED_GRAPH}>\n"
            "WHERE {\n"
            "  ?muni (rdfs:label|schema:name) ?label .\n"
            f"  FILTER(CONTAINS(LCASE(STR(?label)), LCASE(\"{search}\")))\n"
            "}\n"
            f"LIMIT {limit}"
        )
        _LOGGER.debug("Municipality search query built (len=%d)", len(query))
        data = await self._post_query(query)
        bindings = data.get("results", {}).get("bindings", [])
        results: List[Tuple[str, str]] = []
        for b in bindings:
            uri = self._binding_value(b.get("muni", {}))
            label = self._binding_value(b.get("label", {}))
            if uri and label:
                results.append((uri, label))
        _LOGGER.debug("Municipality search got %d results", len(results))
        return results

    async def discover_model(self, sample_limit: int = 2000) -> DiscoveryResult:
        """Heuristically discover predicates for municipality and year.

        Strategy: fetch some observations with all triples and look for predicates
        that match heuristic hints (see constants). For municipality, object is a URI;
        for year, object is a literal integer.
        """
        q = (
            "PREFIX cube: <https://cube.link/>\n"
            "SELECT ?obs ?p ?o ?otype\n"
            f"FROM <{NAMED_GRAPH}>\n"
            "WHERE {\n"
            "  ?obs a cube:Observation .\n"
            "  ?obs ?p ?o .\n"
            "  BIND(DATATYPE(?o) AS ?otype)\n"
            "}\n"
            f"LIMIT {sample_limit}"
        )
        data = await self._post_query(q)
        bindings = data.get("results", {}).get("bindings", [])

        muni_scores: Dict[str, int] = {}
        year_scores: Dict[str, int] = {}
        for b in bindings:
            p = self._binding_value(b.get("p", {}))
            o = b.get("o", {})
            otype = self._binding_value(b.get("otype", {}))
            if not p:
                continue
            pl = p.lower()
            # Municipality: object is URI (type 'uri' in SPARQL result)
            if o.get("type") == "uri":
                if any(hint in pl for hint in MUNICIPALITY_PRED_HINTS):
                    muni_scores[p] = muni_scores.get(p, 0) + 3
                else:
                    # weak hit
                    muni_scores[p] = muni_scores.get(p, 0) + 1
            # Year: literal integer
            if (o.get("type") == "literal" and (otype.endswith("#integer") or o.get("datatype", "").endswith("#integer"))):
                if any(hint in pl for hint in YEAR_PRED_HINTS):
                    year_scores[p] = year_scores.get(p, 0) + 3
                else:
                    year_scores[p] = year_scores.get(p, 0) + 1

        if not muni_scores or not year_scores:
            raise RuntimeError("Could not discover predicates for municipality/year")

        municipality_pred = max(muni_scores.items(), key=lambda kv: kv[1])[0]
        year_pred = max(year_scores.items(), key=lambda kv: kv[1])[0]
        _LOGGER.debug("Discovered predicates: municipality=%s, year=%s", municipality_pred, year_pred)
        return DiscoveryResult(municipality_pred=municipality_pred, year_pred=year_pred)

    async def fetch_observations(self, municipality_uri: str, year: int, preds: DiscoveryResult, limit: int = 200000) -> List[Dict[str, Any]]:
        """Fetch raw observations (triples) for a specific municipality and year."""
        # Use EXISTS filters with discovered predicates for precision
        year_literal = f'"{year}"^^<http://www.w3.org/2001/XMLSchema#integer>'
        q = (
            "PREFIX cube: <https://cube.link/>\n"
            "SELECT ?obs ?p ?o\n"
            f"FROM <{NAMED_GRAPH}>\n"
            "WHERE {\n"
            "  ?obs a cube:Observation .\n"
            "  ?obs ?p ?o .\n"
            f"  FILTER EXISTS {{ ?obs <{preds.municipality_pred}> <{municipality_uri}> }}\n"
            f"  FILTER EXISTS {{ ?obs <{preds.year_pred}> {year_literal} }}\n"
            "}\n"
            f"LIMIT {limit}"
        )
        data = await self._post_query(q)
        bindings: List[Dict[str, Any]] = data.get("results", {}).get("bindings", [])
        return bindings

    @staticmethod
    def _keyword_score(s: str, keywords: Iterable[str]) -> int:
        low = s.lower()
        return sum(1 for k in keywords if k in low)

    def parse_components(self, bindings: List[Dict[str, Any]]) -> Tuple[Dict[str, float], Dict[str, str], List[str], Dict[str, Any]]:
        """Parse triples into component values and units.

        Returns:
        - comp_values: mapping of component -> float
        - units: mapping of component -> unit string
        - raw_obs_ids: list of observation identifiers (subset)
        - extra_meta: any discovered additional info (e.g., profile counts)
        """
        # Group by observation id
        obs: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for b in bindings:
            obs_id = self._binding_value(b.get("obs", {}))
            p = self._binding_value(b.get("p", {}))
            o = b.get("o", {})
            if not obs_id or not p or not o:
                continue
            obs.setdefault(obs_id, []).append((p, o))

        _LOGGER.debug("Parsing %d observations", len(obs))
        comp_values: Dict[str, float] = {}
        units: Dict[str, str] = {}
        raw_ids_subset: List[str] = []
        meta: Dict[str, Any] = {}

        candidates: List[Tuple[str, float, str]] = []  # (component, value, unit)

        for oid, triples in obs.items():
            if len(raw_ids_subset) < 25:
                raw_ids_subset.append(oid)
            # Detect potential unit and value predicates per observation
            text_map: Dict[str, str] = {}
            num_map: Dict[str, float] = {}
            unit_map: Dict[str, str] = {}

            for p, o in triples:
                pl = p.lower()
                if o.get("type") == "literal":
                    val = o.get("value")
                    dt = o.get("datatype", "")
                    if dt.endswith("#decimal") or dt.endswith("#double") or dt.endswith("#float") or dt.endswith("#integer"):
                        try:
                            num_map[p] = float(val)
                        except (ValueError, TypeError):
                            pass
                    else:
                        text_map[p] = str(val)
                else:
                    # URIs we just record as text
                    text_map[p] = o.get("value", "")

            # Try to infer unit from text values mentioning CHF/kWh etc.
            possible_units: List[str] = []
            for p, val in text_map.items():
                unit_score = self._keyword_score(val, ("chf", "kwh", "month", "year", "/kwh", "/month", "/year"))
                if unit_score >= 1 and len(val) <= 20:
                    possible_units.append(val)
                # also predicates can indicate unit
                if self._keyword_score(p, ("unit", "einheit")):
                    possible_units.append(val)

            unit_guess = possible_units[0] if possible_units else "CHF/kWh"

            # Map numeric values to components via predicate keyword matching
            for p, v in num_map.items():
                score_total = self._keyword_score(p, ("total", "gesamt", "sum"))
                score_energy = self._keyword_score(p, ("energy", "arbeit"))
                score_grid = self._keyword_score(p, ("grid", "netz"))
                score_fee = self._keyword_score(p, ("fee", "abgabe"))
                score_meter = self._keyword_score(p, ("meter", "measure", "grund", "base"))

                max_score = max(score_total, score_energy, score_grid, score_fee, score_meter)
                if max_score == 0:
                    # Try a generic price/tarif hint
                    if self._keyword_score(p, ("price", "tarif")) == 0:
                        continue

                component = None
                unit_for_val = unit_guess
                if score_total == max_score:
                    component = "total"
                elif score_energy == max_score:
                    component = "energy"
                elif score_grid == max_score:
                    component = "grid"
                elif score_fee == max_score:
                    component = "fees"
                elif score_meter == max_score:
                    component = "metering"

                if component:
                    candidates.append((component, v, unit_for_val))

        # Reduce candidates: take first-best per component; prefer CHF/kWh for energy/grid/total
        for comp, val, unit in candidates:
            if comp in comp_values:
                continue
            if comp in ("total", "energy", "grid", "fees") and unit.lower().endswith("/kwh"):
                comp_values[comp] = val
                units[comp] = unit
            else:
                # accept first seen
                comp_values.setdefault(comp, val)
                units.setdefault(comp, unit)

        return comp_values, units, raw_ids_subset, meta
