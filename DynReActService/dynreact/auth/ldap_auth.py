import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from ldap3 import Server, Connection, ALL

from dynreact.app import config


LDAP_SPECIAL_CHARACTERS: list[str] = ["*", "(", ")", "&", "!", "("]


ldap_query_pw: str = config.ldap_query_pw
if ldap_query_pw is None:
    ldap_query_pw = os.getenv("LDAP_QUERY_PW")
    if ldap_query_pw is None:
        raise Exception("LDAP_QUERY_PW not specified")
ldap_use_ssl: bool = config.ldap_use_ssl


def ldap_auth(username: str, password: str):
    if len(username) > config.auth_max_user_length:
        return False
    for special_char in LDAP_SPECIAL_CHARACTERS:
        if special_char in username:
            return False
    adds = config.ldap_address
    if isinstance(adds, str):
        adds = [adds]
    for server in adds:
        success = _ldap_auth_internal(username, password, server)
        if success:
            return success
    return False


def _ldap_auth_internal(username: str, password: str, server: str):
    try:
        server = Server(f"ldap://{server}", get_info="NO_INFO", use_ssl=ldap_use_ssl)
        conn = Connection(server, user=str(config.ldap_query_user), password=ldap_query_pw, auto_bind=True)
        # bind (authenticate) the user
        conn.bind()
        bind_success = conn.result['result'] == 0
        if not bind_success:
            return False
        search_result = conn.search(search_base=config.ldap_search_base, search_filter=config.ldap_query.replace("{user}", username), size_limit=1)
        if not search_result or len(conn.response) == 0:
            return False
        results = conn.response
        full_dn = results[0]["dn"]
        # print(" FULL DN", full_dn)
        conn.unbind()
        conn = Connection(server, user=full_dn, password=password, auto_bind=True)
        bind_success = conn.result['result'] == 0
        return bind_success
    except:
        print("Authentication failed at server", server, "user", username)
        return False
    finally:
        try:
            conn.unbind()
        except:
            pass


security = HTTPBasic()


# Dependency to check LDAP authentication
def _check_ldap_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not ldap_auth(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username


ldap_protection = Depends(_check_ldap_auth)

# Example protected route using the dependency
#@app.get("/protected")
#async def protected_route(username: str = Depends(check_ldap_auth)):
#    return {"message": f"Hello, {username}! You have access to this protected route."}
