# Legacy — Azure Functions v4

These files are from the original Azure Functions implementation. The application
has since been migrated to a **FastAPI Container App** (see `app/`).

They are kept here for reference only and are **not used** by the current
application or Docker build.

| File | Original Purpose |
|------|------------------|
| `function_app.py` | Azure Functions v4 entry point (registered blueprints) |
| `host.json` | Azure Functions host configuration |
| `bp_docIntel.py` | Document Intelligence blueprint (`/api/analyze`) |
| `bp_llm.py` | LLM analysis blueprint (`/api/describe`) |
| `bp_doc_llm.py` | Combined Doc Intel + LLM pipeline blueprint |
| `bp_search.py` | Azure AI Search blueprint (`/api/search/*`) |
| `local.settings.example.json` | Azure Functions local settings template |
| `.funcignore` | Azure Functions deployment ignore file |
| `wait_and_apply.sh` | One-off Terraform helper script |
| `services/` | Service layer (blob, LLM summarizer, AI Search) |
