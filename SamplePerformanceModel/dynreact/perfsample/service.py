import random
from typing import Annotated

from dynreact.perfsample.config import ServiceConfig
from dynreact.base.PlantPerformanceModel import PlantPerformanceInput, PerformanceEstimation, PerformanceModelMetadata
from dynreact.base.model import ServiceHealth, Order
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware


config = ServiceConfig()

app = FastAPI(
    title="DynReAct performance sample",
    description="DynReAct sample plant performance model.",
    version="0.0.1",
    contact={
        "name": "VDEh-Betriebsforschungsinstitut (BFI)",
        "url": "https://www.bfi.de",
        "email": "info@bfi.de"
    },
    openapi_tags=[{"name": "dynreact"}],
)
if config.cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

meta = PerformanceModelMetadata(
    id=config.id,
    label=config.label,
    description=config.description,
    processes=config.applicable_processes,
    equipment=config.applicable_equipment
)


def check_secret(token: str|None):
    if config.secret and token != config.secret:
        raise HTTPException(status_code=401, detail="Invalid or missing token")


@app.get("/health",
         tags=["dynreact"],
         response_model_exclude_unset=True,
         response_model_exclude_none=True,
         summary="Service health status")
def health(x_token: Annotated[str | None, Header()] = None) -> ServiceHealth:
    check_secret(x_token)
    return ServiceHealth(status=0)


@app.get("/model",
         tags=["dynreact"],
         response_model_exclude_unset=True,
         response_model_exclude_none=True,
         summary="Plant performance model description")
def model(x_token: Annotated[str | None, Header()] = None) -> PerformanceModelMetadata:
    check_secret(x_token)
    return meta


@app.post("/performance",
          tags=["dynreact"],
          response_model_exclude_unset=True,
          response_model_exclude_none=True,
          summary="Evaluate the plant performance model on some orders, for a fixed plant/equipment.")
def performance(data: PlantPerformanceInput, x_token: Annotated[str | None, Header()] = None) -> list[PerformanceEstimation]:
    check_secret(x_token)

    def performance_for_order(o: Order) -> float:
        if config.feasibility_random_threshold <= 0:
            return 1
        return 0 if random.random() < config.feasibility_random_threshold else 1
    return [PerformanceEstimation(equipment=data.equipment, order=o.id, performance=performance_for_order(o)) for o in data.orders]


