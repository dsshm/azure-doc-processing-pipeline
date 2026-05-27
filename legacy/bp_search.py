import logging
import json
import azure.functions as func

from services import SearchService

bp_search = func.Blueprint()


@bp_search.route(route="search/setup", methods=["POST"])
def setup_search(req: func.HttpRequest) -> func.HttpResponse:
    """Create or update the search index, data source, skillset, and indexer."""
    try:
        svc = SearchService()
        results = svc.setup()

        return func.HttpResponse(
            body=json.dumps({"status": "ok", "resources": results}),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"Search setup failed: {e}")
        return func.HttpResponse(
            body=json.dumps({"error": "Search setup failed", "details": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


@bp_search.route(route="search/indexer/run", methods=["POST"])
def run_indexer(req: func.HttpRequest) -> func.HttpResponse:
    """Trigger an on-demand indexer run."""
    try:
        svc = SearchService()
        svc.run_indexer()

        return func.HttpResponse(
            body=json.dumps({"status": "ok", "message": "Indexer run triggered"}),
            status_code=202,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"Failed to run indexer: {e}")
        return func.HttpResponse(
            body=json.dumps({"error": "Failed to run indexer", "details": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


@bp_search.route(route="search/indexer/status", methods=["GET"])
def indexer_status(req: func.HttpRequest) -> func.HttpResponse:
    """Get current indexer status."""
    try:
        svc = SearchService()
        status = svc.get_indexer_status()

        return func.HttpResponse(
            body=json.dumps(status),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"Failed to get indexer status: {e}")
        return func.HttpResponse(
            body=json.dumps({"error": "Failed to get indexer status", "details": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


@bp_search.route(route="search/indexer/reset", methods=["POST"])
def reset_indexer(req: func.HttpRequest) -> func.HttpResponse:
    """Reset the indexer to re-process all documents."""
    try:
        svc = SearchService()
        svc.reset_indexer()

        return func.HttpResponse(
            body=json.dumps({"status": "ok", "message": "Indexer reset"}),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"Failed to reset indexer: {e}")
        return func.HttpResponse(
            body=json.dumps({"error": "Failed to reset indexer", "details": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


@bp_search.route(route="search/query", methods=["POST"])
def search_query(req: func.HttpRequest) -> func.HttpResponse:
    """
    Execute a search query.

    Request body:
    {
        "query": "search text",
        "mode": "hybrid" | "fulltext" | "vector",
        "filter": "<OData filter>",    // optional
        "top": 10,                      // optional
        "select": ["field1", "field2"], // optional
        "facets": ["docType", "topics"] // optional
    }
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            body=json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    query = body.get("query")
    if not query:
        return func.HttpResponse(
            body=json.dumps({"error": "Missing 'query' in request body"}),
            status_code=400,
            mimetype="application/json",
        )

    mode = body.get("mode", "hybrid")
    if mode not in ("fulltext", "vector", "hybrid"):
        return func.HttpResponse(
            body=json.dumps({"error": "mode must be 'fulltext', 'vector', or 'hybrid'"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        svc = SearchService()
        results = svc.search(
            query=query,
            search_mode=mode,
            filters=body.get("filter"),
            top=body.get("top", 10),
            select=body.get("select"),
            facets=body.get("facets"),
        )

        return func.HttpResponse(
            body=json.dumps(results, default=str),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"Search query failed: {e}")
        return func.HttpResponse(
            body=json.dumps({"error": "Search query failed", "details": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


@bp_search.route(route="search/chunks", methods=["POST"])
def search_chunks(req: func.HttpRequest) -> func.HttpResponse:
    """
    Search the chunks index for granular passage-level retrieval.

    Request body:
    {
        "query": "search text",
        "mode": "hybrid" | "fulltext" | "vector",
        "filter": "<OData filter>",
        "top": 10
    }
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            body=json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    query = body.get("query")
    if not query:
        return func.HttpResponse(
            body=json.dumps({"error": "Missing 'query' in request body"}),
            status_code=400,
            mimetype="application/json",
        )

    mode = body.get("mode", "hybrid")
    if mode not in ("fulltext", "vector", "hybrid"):
        return func.HttpResponse(
            body=json.dumps({"error": "mode must be 'fulltext', 'vector', or 'hybrid'"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        svc = SearchService()
        results = svc.search_chunks(
            query=query,
            search_mode=mode,
            filters=body.get("filter"),
            top=body.get("top", 10),
        )

        return func.HttpResponse(
            body=json.dumps(results, default=str),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"Chunk search failed: {e}")
        return func.HttpResponse(
            body=json.dumps({"error": "Chunk search failed", "details": str(e)}),
            status_code=500,
            mimetype="application/json",
        )
