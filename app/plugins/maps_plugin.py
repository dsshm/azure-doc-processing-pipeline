"""Azure Maps fuzzy search integration.

Auth: DefaultAzureCredential with Microsoft Entra ID and Azure Maps RBAC.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

_AZURE_MAPS_SCOPE = "https://atlas.microsoft.com/.default"
_TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class AzureMapsError(RuntimeError):
    """Raised when Azure Maps fuzzy search fails."""


class AzureMapsPlugin:
    """Small Azure Maps REST wrapper for fuzzy geocoding extracted locations."""

    def __init__(
        self,
        endpoint: str | None = None,
        client_id: str | None = None,
        country_set: str | None = None,
        language: str | None = None,
        limit: int | None = None,
        max_fuzzy_level: int | None = None,
        timeout_seconds: int | None = None,
        max_retries: int = 3,
    ):
        self._endpoint = (endpoint or os.getenv("AZURE_MAPS_ENDPOINT", "https://atlas.microsoft.com")).rstrip("/")
        self._client_id = client_id or os.getenv("AZURE_MAPS_CLIENT_ID", "")
        self._country_set = country_set or os.getenv("AZURE_MAPS_COUNTRY_SET", "US")
        self._language = language or os.getenv("AZURE_MAPS_LANGUAGE", "en-US")
        self._limit = limit or int(os.getenv("AZURE_MAPS_FUZZY_SEARCH_LIMIT", "1"))
        self._max_fuzzy_level = max_fuzzy_level or int(os.getenv("AZURE_MAPS_MAX_FUZZY_LEVEL", "1"))
        self._timeout_seconds = timeout_seconds or int(os.getenv("AZURE_MAPS_TIMEOUT_SECONDS", "10"))
        self._max_retries = max_retries
        self._credential = DefaultAzureCredential()

    @property
    def is_configured(self) -> bool:
        return bool(self._client_id)

    def fuzzy_search(self, query: str) -> dict[str, Any] | None:
        """Return the best Azure Maps fuzzy-search match for a location query."""
        normalized_query = query.strip()
        if not normalized_query:
            return None
        if not self.is_configured:
            raise AzureMapsError("AZURE_MAPS_CLIENT_ID is not configured")

        payload = self._request_fuzzy_search(normalized_query)
        results = payload.get("results") or []
        if not results:
            logger.info("Azure Maps returned no fuzzy-search results for '%s'", normalized_query)
            return None

        parsed = self._parse_result(normalized_query, results[0])
        if not parsed:
            logger.info("Azure Maps top fuzzy-search result for '%s' had no usable position", normalized_query)
        return parsed

    def _request_fuzzy_search(self, query: str) -> dict[str, Any]:
        params = {
            "api-version": "1.0",
            "query": query,
            "limit": self._limit,
            "language": self._language,
            "maxFuzzyLevel": self._max_fuzzy_level,
        }
        if self._country_set:
            params["countrySet"] = self._country_set

        url = f"{self._endpoint}/search/fuzzy/json?{urlencode(params)}"
        token = self._credential.get_token(_AZURE_MAPS_SCOPE).token
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "x-ms-client-id": self._client_id,
            },
            method="GET",
        )

        for attempt in range(1, self._max_retries + 1):
            try:
                with urlopen(request, timeout=self._timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in _TRANSIENT_STATUS_CODES and attempt < self._max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise AzureMapsError(f"Azure Maps fuzzy search failed with HTTP {exc.code}: {body}") from exc
            except URLError as exc:
                if attempt < self._max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise AzureMapsError(f"Azure Maps fuzzy search request failed: {exc.reason}") from exc

        raise AzureMapsError("Azure Maps fuzzy search retry loop exited unexpectedly")

    def _sleep_before_retry(self, attempt: int) -> None:
        delay_seconds = min(2 ** (attempt - 1), 8)
        logger.warning("Retrying Azure Maps fuzzy search after transient failure (attempt %d)", attempt)
        time.sleep(delay_seconds)

    def _parse_result(self, query: str, result: dict[str, Any]) -> dict[str, Any] | None:
        position = result.get("position") or {}
        latitude = position.get("lat")
        longitude = position.get("lon")
        if latitude is None or longitude is None:
            return None

        address = result.get("address") or {}
        poi = result.get("poi") or {}
        formatted_address = address.get("freeformAddress") or address.get("municipality") or ""

        return {
            "query": query,
            "latitude": latitude,
            "longitude": longitude,
            "formatted_address": formatted_address,
            "display_name": poi.get("name") or formatted_address or query,
            "result_type": result.get("type", ""),
            "score": result.get("score"),
            "source": "azure_maps_fuzzy_search",
        }
