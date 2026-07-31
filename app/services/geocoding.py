"""Shared Azure Maps geocoding helpers for extracted locations."""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.plugins.maps_plugin import AzureMapsError

logger = logging.getLogger(__name__)

US_STATE_NAMES = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
}
US_STATE_ABBREVIATIONS = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
}
ADDRESS_HINT_RE = re.compile(
    r"\d|(?:\b(?:ave|avenue|st|street|rd|road|blvd|boulevard|dr|drive|ln|lane|ct|court|pkwy|parkway)\b)",
    re.IGNORECASE,
)
PHONE_LIKE_RE = re.compile(r"^\+?[\d\s().-]{7,}$")


class MapsGeocoder(Protocol):
    @property
    def is_configured(self) -> bool: ...

    def fuzzy_search(self, query: str) -> dict[str, Any] | None: ...


@dataclass
class GeocodingAssessment:
    needs_update: bool
    reasons: list[str] = field(default_factory=list)
    location_queries_total: int = 0
    geocoded_locations_total: int = 0
    invalid_geocoded_locations: int = 0
    maps_configured: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "needs_update": self.needs_update,
            "reasons": self.reasons,
            "location_queries_total": self.location_queries_total,
            "geocoded_locations_total": self.geocoded_locations_total,
            "invalid_geocoded_locations": self.invalid_geocoded_locations,
            "maps_configured": self.maps_configured,
        }


@dataclass
class GeocodingResult:
    document: dict[str, Any]
    changed: bool
    reasons: list[str] = field(default_factory=list)
    location_queries_total: int = 0
    geocoded_locations_added: int = 0
    geocoded_locations_total: int = 0
    removed_invalid_geocoded_locations: int = 0
    failed_geocoding_queries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "geocoding_changed": self.changed,
            "geocoding_reasons": self.reasons,
            "location_queries_total": self.location_queries_total,
            "geocoded_locations_added": self.geocoded_locations_added,
            "geocoded_locations_total": self.geocoded_locations_total,
            "removed_invalid_geocoded_locations": self.removed_invalid_geocoded_locations,
            "failed_geocoding_queries": self.failed_geocoding_queries,
        }


def assess_geocoding(document: dict[str, Any], maps: MapsGeocoder) -> GeocodingAssessment:
    """Check whether stored result data has usable geocoded locations."""
    queries = collect_location_queries(document)
    geocoded_locations = _get_geocoded_locations(document)
    valid_geocoded_locations = [item for item in geocoded_locations if _has_coordinates(item)]
    invalid_count = len(geocoded_locations) - len(valid_geocoded_locations)

    reasons: list[str] = []
    if queries and not valid_geocoded_locations:
        reasons.append("geocoded_locations_missing")
    if invalid_count:
        reasons.append("geocoded_locations_invalid")
    if reasons and not maps.is_configured:
        reasons.append("azure_maps_not_configured")

    return GeocodingAssessment(
        needs_update=bool(reasons),
        reasons=reasons,
        location_queries_total=len(queries),
        geocoded_locations_total=len(valid_geocoded_locations),
        invalid_geocoded_locations=invalid_count,
        maps_configured=maps.is_configured,
    )


def apply_geocoding(
    document: dict[str, Any],
    maps: MapsGeocoder,
    fail_when_unconfigured: bool = False,
    fail_fast: bool = False,
) -> GeocodingResult:
    """Attach Azure Maps coordinates to key_fields.entities.geocoded_locations."""
    updated = copy.deepcopy(document)
    assessment = assess_geocoding(updated, maps)
    if not assessment.needs_update:
        return GeocodingResult(
            document=updated,
            changed=False,
            reasons=assessment.reasons,
            location_queries_total=assessment.location_queries_total,
            geocoded_locations_total=assessment.geocoded_locations_total,
            removed_invalid_geocoded_locations=assessment.invalid_geocoded_locations,
        )

    key_fields = updated.get("key_fields")
    if not isinstance(key_fields, dict):
        return GeocodingResult(document=updated, changed=False, reasons=assessment.reasons)

    entities = key_fields.get("entities")
    if not isinstance(entities, dict):
        return GeocodingResult(document=updated, changed=False, reasons=assessment.reasons)

    queries = collect_location_queries(updated)
    if queries and not maps.is_configured:
        if fail_when_unconfigured:
            raise AzureMapsError("AZURE_MAPS_CLIENT_ID is not configured")
        logger.info("Azure Maps geocoding skipped because AZURE_MAPS_CLIENT_ID is not configured")
        return GeocodingResult(
            document=updated,
            changed=False,
            reasons=assessment.reasons,
            location_queries_total=len(queries),
            geocoded_locations_total=assessment.geocoded_locations_total,
            removed_invalid_geocoded_locations=assessment.invalid_geocoded_locations,
        )

    geocoded_locations = [
        item
        for item in entities.get("geocoded_locations") or []
        if isinstance(item, dict) and _has_coordinates(item)
    ]
    removed_invalid = assessment.invalid_geocoded_locations
    existing_queries = {
        item.get("query", "").strip().casefold()
        for item in geocoded_locations
        if isinstance(item.get("query"), str)
    }
    existing_result_keys: set[tuple[float, float] | str] = set()
    has_precise_geocode = False
    for item in geocoded_locations:
        existing_result_keys.update(_geocode_result_keys(item))
        if not _is_geography_result(item):
            has_precise_geocode = True

    added = 0
    failed = 0
    for query in queries:
        if query.casefold() in existing_queries:
            continue
        try:
            geocoded = maps.fuzzy_search(query)
        except AzureMapsError as exc:
            logger.warning("Azure Maps geocoding failed for '%s': %s", query, exc)
            if fail_fast:
                raise
            failed += 1
            continue
        if not geocoded:
            continue

        result_keys = _geocode_result_keys(geocoded)
        if _is_geography_result(geocoded) and has_precise_geocode:
            existing_queries.add(query.casefold())
            continue
        if result_keys & existing_result_keys:
            existing_queries.add(query.casefold())
            continue

        geocoded_locations.append(geocoded)
        existing_queries.add(query.casefold())
        existing_result_keys.update(result_keys)
        if not _is_geography_result(geocoded):
            has_precise_geocode = True
        added += 1

    changed = bool(added or removed_invalid)
    if changed:
        entities["geocoded_locations"] = geocoded_locations
        key_fields["entities"] = entities
        updated["key_fields"] = key_fields

    reasons = list(assessment.reasons)
    return GeocodingResult(
        document=updated,
        changed=changed,
        reasons=reasons,
        location_queries_total=len(queries),
        geocoded_locations_added=added,
        geocoded_locations_total=len(geocoded_locations),
        removed_invalid_geocoded_locations=removed_invalid,
        failed_geocoding_queries=failed,
    )


def collect_location_queries(document: dict[str, Any]) -> list[str]:
    """Build Azure Maps fuzzy-search queries from stored extraction output."""
    queries: list[str] = []
    seen: set[str] = set()
    locations: list[str] = []
    organizations: list[str] = []
    evidence_quotes: list[str] = []

    def add_query(value: Any) -> None:
        if not isinstance(value, str):
            return
        query = value.strip()
        key = query.casefold()
        if query and key not in seen:
            queries.append(query)
            seen.add(key)

    def add_unique(items: list[str], value: Any) -> None:
        if not isinstance(value, str):
            return
        normalized = value.strip()
        if normalized and normalized.casefold() not in {item.casefold() for item in items}:
            items.append(normalized)

    key_fields = document.get("key_fields")
    if isinstance(key_fields, dict):
        entities = key_fields.get("entities")
        if isinstance(entities, dict):
            for location in entities.get("locations") or []:
                add_unique(locations, location)
            for organization in entities.get("organizations") or []:
                add_unique(organizations, organization)

    for entity in document.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        entity_type = entity.get("type")
        if entity_type == "location":
            add_unique(locations, entity.get("entity"))
            for evidence in entity.get("supporting_evidence") or []:
                if isinstance(evidence, dict):
                    add_unique(evidence_quotes, evidence.get("quote"))
        elif entity_type == "organization":
            add_unique(organizations, entity.get("entity"))

    location_context = _build_location_context(locations)
    rich_query_added = False

    for quote in evidence_quotes:
        if _is_address_like(quote) and len(quote) <= 160 and "http" not in quote.casefold():
            add_query(quote)
            rich_query_added = True

    for location in locations:
        if not _is_address_like(location):
            continue
        if location_context and location_context.casefold() not in location.casefold():
            add_query(f"{location}, {location_context}")
        else:
            add_query(location)
        rich_query_added = True

    if location_context:
        organization = _best_organization_candidate(document, organizations)
        if organization:
            add_query(f"{organization}, {location_context}")
            rich_query_added = True

    if location_context:
        add_query(location_context)

    if not rich_query_added:
        for location in locations:
            if not _is_broad_location(location):
                add_query(location)

    return queries


def _get_geocoded_locations(document: dict[str, Any]) -> list[dict[str, Any]]:
    key_fields = document.get("key_fields")
    if not isinstance(key_fields, dict):
        return []
    entities = key_fields.get("entities")
    if not isinstance(entities, dict):
        return []
    return [item for item in entities.get("geocoded_locations") or [] if isinstance(item, dict)]


def _build_location_context(locations: list[str]) -> str:
    address_locations = [location for location in locations if _is_address_like(location)]
    non_address_locations = [location for location in locations if location not in address_locations]

    for location in non_address_locations:
        if "," in location:
            return location

    states = [location for location in non_address_locations if _is_us_state(location)]
    cities = [
        location
        for location in non_address_locations
        if not _is_us_state(location) and not _is_broad_location(location)
    ]
    if not cities:
        cities = [location for location in non_address_locations if not _is_us_state(location)]

    if cities and states:
        return f"{cities[0]}, {states[0]}"
    if cities:
        return cities[0]
    if states and not address_locations:
        return states[0]
    return ""


def _is_address_like(value: str) -> bool:
    return bool(ADDRESS_HINT_RE.search(value))


def _is_broad_location(value: str) -> bool:
    return not _is_address_like(value) and "," not in value and len(value.split()) <= 1


def _is_us_state(value: str) -> bool:
    normalized = value.strip()
    return normalized.casefold() in US_STATE_NAMES or normalized.upper() in US_STATE_ABBREVIATIONS


def _is_searchable_organization(value: str) -> bool:
    normalized = value.strip()
    return bool(normalized) and not PHONE_LIKE_RE.match(normalized)


def _best_organization_candidate(document: dict[str, Any], organizations: list[str]) -> str:
    candidates = [organization for organization in organizations if _is_searchable_organization(organization)]
    if not candidates:
        return ""

    title = document.get("title")
    if isinstance(title, str) and title:
        title_key = title.casefold()
        for organization in candidates:
            if organization.casefold() in title_key:
                return organization
    return candidates[0]


def _geocode_result_keys(item: dict[str, Any]) -> set[tuple[float, float] | str]:
    keys: set[tuple[float, float] | str] = set()
    latitude = item.get("latitude")
    longitude = item.get("longitude")
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        keys.add((round(float(latitude), 4), round(float(longitude), 4)))
    formatted_address = item.get("formatted_address")
    if isinstance(formatted_address, str) and formatted_address:
        keys.add(formatted_address.casefold())
    return keys


def _is_geography_result(item: dict[str, Any]) -> bool:
    result_type = item.get("result_type")
    return isinstance(result_type, str) and result_type.casefold() == "geography"


def _has_coordinates(item: dict[str, Any]) -> bool:
    return isinstance(item.get("latitude"), (int, float)) and isinstance(item.get("longitude"), (int, float))
