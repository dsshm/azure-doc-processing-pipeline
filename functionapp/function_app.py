from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import azure.functions as func
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

_credential = DefaultAzureCredential()

ALLOWED_MODES = {"hybrid", "full-text", "vector"}
ALLOWED_VECTOR_FIELDS = {"summary_vector", "purpose_vector"}


class SearchRequestValidationError(ValueError):
    """Validation error whose message is safe to return to callers."""


@app.function_name(name="SearchDocuments")
@app.route(route="SearchDocuments", methods=["POST"])
def search_documents(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP facade for Power Platform search clients."""
    try:
        body = req.get_json()
    except ValueError:
        logging.warning("SearchDocuments request body was not valid JSON.", exc_info=True)
        return _json_response({"error": "Request body must be valid JSON."}, status_code=400)

    if not isinstance(body, dict):
        return _json_response({"error": "Request body must be a JSON object."}, status_code=400)

    try:
        query = _resolve_query(body)
        top = _resolve_top(body)
        mode = _resolve_mode(body)
        vector_field = _resolve_vector_field(body)
    except SearchRequestValidationError as exc:
        logging.warning("SearchDocuments request validation failed.", exc_info=True)
        return _json_response({"error": str(exc)}, status_code=400)
    except ValueError:
        logging.exception("Unexpected SearchDocuments request validation failure.")
        return _json_response({"error": "Invalid search request."}, status_code=400)

    if mode == "full-text":
        status_code, response_body = _call_container_search(
            path="/api/search/full-text",
            body={
                "query": query,
                "top": top,
            },
        )
        return _proxy_response(response_body, status_code, search_mode="full-text")

    embedding = _try_create_embedding(query)
    if embedding is None:
        status_code, response_body = _call_container_search(
            path="/api/search/full-text",
            body={
                "query": query,
                "top": top,
            },
        )
        return _proxy_response(
            response_body,
            status_code,
            search_mode="full-text-fallback",
            fallback_reason="embedding-unavailable",
        )

    if mode == "vector":
        status_code, response_body = _call_container_search(
            path="/api/search/vector",
            body={
                "query": query,
                "top": top,
                "vector_field": vector_field,
                "query_vector": embedding,
            },
        )
        return _proxy_response(response_body, status_code, search_mode="vector")

    status_code, response_body = _call_container_search(
        path="/api/search/hybrid/vector",
        body={
            "query": query,
            "top": top,
            "vector_field": vector_field,
            "query_vector": embedding,
        },
    )
    return _proxy_response(response_body, status_code, search_mode="hybrid")


def _resolve_query(body: dict[str, Any]) -> str:
    query = str(body.get("query") or "").strip()
    if not query:
        raise SearchRequestValidationError("query must not be empty")
    return query


def _resolve_top(body: dict[str, Any]) -> int:
    raw_top = body.get("top")
    try:
        top = int(os.getenv("SEARCH_DEFAULT_TOP", "30")) if raw_top is None else int(raw_top)
    except (TypeError, ValueError) as exc:
        raise SearchRequestValidationError("top must be an integer") from exc

    if top < 1:
        raise SearchRequestValidationError("top must be at least 1")

    max_top = int(os.getenv("SEARCH_MAX_TOP", "1000"))
    if top > max_top:
        raise SearchRequestValidationError(f"top exceeds configured SEARCH_MAX_TOP ({max_top})")

    return top


def _resolve_mode(body: dict[str, Any]) -> str:
    mode = str(body.get("mode") or "hybrid").strip().lower()
    if mode not in ALLOWED_MODES:
        raise SearchRequestValidationError("mode must be one of: hybrid, full-text, vector")
    return mode


def _resolve_vector_field(body: dict[str, Any]) -> str:
    vector_field = str(body.get("vector_field") or os.getenv("SEARCH_DEFAULT_VECTOR_FIELD", "summary_vector")).strip()
    if vector_field not in ALLOWED_VECTOR_FIELDS:
        raise SearchRequestValidationError("vector_field must be one of: summary_vector, purpose_vector")
    return vector_field


def _try_create_embedding(query: str) -> list[float] | None:
    endpoint = _required_setting("AZURE_OPENAI_ENDPOINT").rstrip("/")
    deployment = _required_setting("AZURE_OPENAI_EMBEDDING_MODEL")
    api_version = _required_setting("AZURE_OPENAI_EMBEDDING_API_VERSION")
    url = f"{endpoint}/openai/deployments/{deployment}/embeddings?api-version={api_version}"

    try:
        token = _credential.get_token("https://cognitiveservices.azure.com/.default").token
        status_code, response_body = _post_json(
            url=url,
            body={"input": query},
            headers={"Authorization": f"Bearer {token}"},
        )
        if status_code != 200:
            logging.warning("Embedding request returned status %s: %s", status_code, response_body.decode("utf-8", "replace"))
            return None

        payload = json.loads(response_body)
        embedding = payload.get("data", [{}])[0].get("embedding")
        if not isinstance(embedding, list) or not embedding:
            logging.warning("Embedding response did not include a usable vector.")
            return None
        return embedding
    except (AzureError, HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        logging.warning("Embedding request failed; falling back to full-text search: %s", exc)
        return None


def _call_container_search(path: str, body: dict[str, Any]) -> tuple[int, bytes]:
    try:
        base_url = _required_setting("CONTAINER_APP_BASE_URL").rstrip("/")
        return _post_json(
            url=f"{base_url}{path}",
            body=body,
            headers={},
        )
    except (HTTPError, URLError, TimeoutError, ValueError):
        logging.exception("Container App search call failed.")
        return 502, json.dumps({"error": "Search service is temporarily unavailable."}).encode("utf-8")


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str]) -> tuple[int, bytes]:
    request_headers = {
        "Content-Type": "application/json",
        **headers,
    }
    request = Request(
        url=url,
        method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers=request_headers,
    )

    try:
        with urlopen(request, timeout=_request_timeout_seconds()) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def _request_timeout_seconds() -> int:
    return int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))


def _required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required app setting: {name}")
    return value


def _proxy_response(
    body: bytes,
    status_code: int,
    search_mode: str,
    fallback_reason: str | None = None,
) -> func.HttpResponse:
    headers = {
        "Content-Type": "application/json",
        "x-docpipeline-search-mode": search_mode,
    }
    if fallback_reason:
        headers["x-docpipeline-fallback-reason"] = fallback_reason
    return func.HttpResponse(body=body, status_code=status_code, headers=headers)


def _json_response(body: dict[str, Any], status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(body).encode("utf-8"),
        status_code=status_code,
        headers={"Content-Type": "application/json"},
    )
