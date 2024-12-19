from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from ldap3 import Server, Connection, ALL

from dynreact.app import config


LDAP_SPECIAL_CHARACTERS: list[str] = ["*", "(", ")", "&", "!", "("]


def ldap_auth_simple(username: str, password: str):
    if len(username) > config.auth_max_user_length:
        return False
    for special_char in LDAP_SPECIAL_CHARACTERS:
        if special_char in username:
            return False
    did_connect: bool = False
    try:
        server = Server(f"ldap://{config.ldap_address}", get_info=ALL)
        conn = Connection(server, user=f"cn={username},{config.ldap_user_extension}", password=password, auto_bind=True)
        # bind (authenticate) the user
        conn.bind()
        if conn.result['result'] == 0:
            print("Authentication successful")
            did_connect = True
    except:
        print("Authentication failed")
    finally:
        try:
            conn.unbind()
        except:
            pass
    return did_connect


security = HTTPBasic()


# Dependency to check LDAP authentication
def _check_ldap_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not ldap_auth_simple(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username


ldap_simple_protection = Depends(_check_ldap_auth)

# Example protected route using the dependency
#@app.get("/protected")
#async def protected_route(username: str = Depends(check_ldap_auth)):
#    return {"message": f"Hello, {username}! You have access to this protected route."}
