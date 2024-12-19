import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials


# Configure a user and password via env vars for testing

configured_user = os.getenv("DUMMY_USER")
configured_pw   = os.getenv("DUMMY_PW")

if configured_user is None or configured_pw is None:
    raise Exception("Dummy user and/or pw not configured (env DUMMY_USER, DUMMY_PW)")


def dummy_auth(username: str, password: str):
    return username == configured_user and password == configured_pw


security = HTTPBasic()


# Dependency to check dummy authentication
def _check_dummy_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not dummy_auth(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username


dummy_protection = Depends(_check_dummy_auth)


