from starlette.middleware.wsgi import WSGIMiddleware

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"), override=True)

from dynreact.gui.dash_app import app
from dynreact.service.service import fastapi_app

fastapi_app.mount("/dash", WSGIMiddleware(app.server))
