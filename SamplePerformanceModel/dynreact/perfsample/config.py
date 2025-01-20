import os
from dotenv import load_dotenv


class ServiceConfig:

    secret: str
    feasibility_random_threshold: float = 0
    cors: bool = False

    def __init__(self, secret: str|None=None, feasibility_random_threshold: float|None = None, cors: bool|None = None):
        load_dotenv()
        if secret is None:
            secret = os.getenv("SECRET")
        self.secret = secret
        if feasibility_random_threshold is None:
            feasibility_random_threshold = float(os.getenv("FEASIBILITY_RANDOM_THRESHOLD", self.feasibility_random_threshold))
        self.feasibility_random_threshold = feasibility_random_threshold
        if cors is None:
            cors = os.getenv("CORS", "false").lower() == "true"
        self.cors = cors
