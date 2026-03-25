from starlette.middleware.wsgi import WSGIMiddleware

# Added by JOM for Debugging 
import os
from pathlib import Path
import debugpy
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"), override=True)

from dynreact.gui.dash_app import app
from dynreact.service.service import fastapi_app

# Debugging remote connection setup
if os.getenv("DEBUG_ENABLED") == "true":
    DEBUG_PORT = int(os.getenv("DEBUG_PORT", "5678"))
    debugpy.listen(("0.0.0.0", DEBUG_PORT))
    print(f"Waiting for debugger on port {DEBUG_PORT}...")
    debugpy.wait_for_client()

fastapi_app.mount("/dash", WSGIMiddleware(app.server))
