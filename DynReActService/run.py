from starlette.middleware.wsgi import WSGIMiddleware

from dynreact.gui.dash_app import app
from dynreact.service.service import fastapi_app


fastapi_app.mount("/dash", WSGIMiddleware(app.server))

