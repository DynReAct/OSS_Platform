import os
import uuid

from dotenv import load_dotenv


class ServiceConfig:

    id: str
    label: str
    description: str|None=None
    applicable_processes: list[str]|None=None
    applicable_equipment: list[int] | None = None
    secret: str
    feasibility_random_threshold: float = 0
    cors: bool = False

    def __init__(self,
                 id: str|None=None,
                 label: str|None=None,
                 description: str | None = None,
                 applicable_processes: list[str] | None = None,
                 applicable_equipment: list[int] | None = None,
                 secret: str|None=None,
                 feasibility_random_threshold: float|None = None,
                 cors: bool|None = None):
        load_dotenv()
        if id is None:
            id = os.getenv("MODEL_ID")
            if id is None:
                id = uuid.uuid4().hex
        self.id = id
        if label is None:
            label = os.getenv("MODEL_LABEL")
            if label is None:
                label = id
        self.label = label
        if description is None:
            description = os.getenv("MODEL_DESCRIPTION")
        self.description = description
        if secret is None:
            secret = os.getenv("SECRET")
        self.secret = secret
        if feasibility_random_threshold is None:
            feasibility_random_threshold = float(os.getenv("FEASIBILITY_RANDOM_THRESHOLD", self.feasibility_random_threshold))
        self.feasibility_random_threshold = feasibility_random_threshold
        if cors is None:
            cors = os.getenv("CORS", "false").lower() == "true"
        self.cors = cors
        if applicable_processes is None:
            procs = os.getenv("APPLICABLE_PROCESSES")
            if procs is not None:
                applicable_processes = [p for p in (p.strip() for p in procs.split(",")) if p != ""]
                if len(applicable_processes) == 0:
                    applicable_processes = None
        self.applicable_processes = applicable_processes
        if applicable_equipment is None:
            procs = os.getenv("APPLICABLE_EQUIPMENT")
            if procs is not None:
                applicable_equipment = [int(p) for p in (p.strip() for p in procs.split(",")) if p != ""]
                if len(applicable_equipment) == 0:
                    applicable_equipment = None
        self.applicable_equipment = applicable_equipment
