import azure.functions as func
import logging, os, json
from datetime import datetime
from typing import Any, Dict

## Function initialization ##
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# --- Import Blueprint Functions ---
from bp_docIntel import docintel
from bp_llm import bp_llm

# --- Register Blueprint Functions ---
app.register_blueprint(docintel)
app.register_blueprint(bp_llm)


