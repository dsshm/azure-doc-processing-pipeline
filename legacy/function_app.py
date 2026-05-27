import azure.functions as func
import logging, os, json
from datetime import datetime
from typing import Any, Dict

## Function initialization ##
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# --- Import Blueprint Functions ---
from bp_docIntel import docintel
from bp_llm import bp_llm
from bp_search import bp_search

# --- Register Blueprint Functions ---
app.register_blueprint(docintel)
app.register_blueprint(bp_llm)
app.register_blueprint(bp_search)


