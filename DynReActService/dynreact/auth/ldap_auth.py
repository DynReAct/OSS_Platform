import os
from functools import lru_cache

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from ldap3 import Server, Connection, ALL

from dynreact.app_config import DynReActSrvConfig

LDAP_SPECIAL_CHARACTERS: list[str] = ["*", "(", ")", "&", "!", "("]


def get_ldap_auth(config: DynReActSrvConfig):

    ldap_query_pw: str = config.ldap_query_pw
    if ldap_query_pw is None:
        ldap_query_pw = os.getenv("LDAP_QUERY_PW")
        if ldap_query_pw is None:
            raise Exception("LDAP_QUERY_PW not specified")
    ldap_use_ssl: bool = config.ldap_use_ssl
    ldap_use_permissions: bool = config.ldap_permissions is not None and len(config.ldap_permissions) > 0

    def _ldap_auth_internal(username: str, password: str, server: str):
        conn = None
        try:
            protocol = "ldap" if not ldap_use_ssl else "ldaps"
            server = Server(f"{protocol}://{server}", get_info="NO_INFO", use_ssl=ldap_use_ssl)
            conn = Connection(server, user=str(config.ldap_query_user), password=ldap_query_pw, auto_bind=True)
            # bind (authenticate) the user
            bind_success = conn.result['result'] == 0
            if not bind_success:
                return False
            search_result = conn.search(search_base=config.ldap_search_base,
                                        search_filter=config.ldap_query.replace("{user}", username), size_limit=1)
            if not search_result or len(conn.response) == 0:
                return False
            results = conn.response
            result = results[0]
            full_dn = result["dn"]
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
    return ldap_auth


def get_permissions_check(config: DynReActSrvConfig):

    ldap_query_pw: str = config.ldap_query_pw
    if ldap_query_pw is None:
        ldap_query_pw = os.getenv("LDAP_QUERY_PW")
        if ldap_query_pw is None:
            raise Exception("LDAP_QUERY_PW not specified")
    ldap_use_ssl: bool = config.ldap_use_ssl
    ldap_use_permissions: bool = config.ldap_permissions is not None and len(config.ldap_permissions) > 0

    @lru_cache(maxsize=64)
    def _ldap_has_permission(username: str, permission_dist_name: str, server: str):
        conn = None
        try:
            protocol = "ldap" if not ldap_use_ssl else "ldaps"
            server = Server(f"{protocol}://{server}", get_info="NO_INFO", use_ssl=ldap_use_ssl)
            conn = Connection(server, user=str(config.ldap_query_user), password=ldap_query_pw, auto_bind=True)
            # bind (authenticate) the user
            bind_success = conn.result['result'] == 0
            if not bind_success:
                return False
            search_filter = config.ldap_query.replace("{user}", username)
            search_filter = f"(&{search_filter}(memberOf={permission_dist_name}))"
            search_result = conn.search(search_base=config.ldap_search_base, search_filter=search_filter, size_limit=1)
            if not search_result or len(conn.response) == 0:
                return False
            result = conn.response[0]
            return "dn" in result and "type" in result and result["type"] == "searchResEntry"
        except:
            return False
        finally:
            try:
                conn.unbind()
            except:
                pass

    def ldap_has_permission(permission: str, username: str) -> bool:
        if not ldap_use_permissions:
            return True
        permission_dist_name = config.ldap_permissions.get(permission)
        if permission_dist_name is None:
            return False
        if len(username) > config.auth_max_user_length:
            return False
        for special_char in LDAP_SPECIAL_CHARACTERS:
            if special_char in username:
                return False
        adds = config.ldap_address
        if isinstance(adds, str):
            adds = [adds]
        for server in adds:
            success = _ldap_has_permission(username, permission_dist_name, server)
            if success:
                return success
        return False
    return ldap_has_permission


def get_ldap_protection(config: DynReActSrvConfig):

    security = HTTPBasic()
    ldap_auth = get_ldap_auth(config)

    # Dependency to check LDAP authentication
    def _check_ldap_auth(credentials: HTTPBasicCredentials = Depends(security)):
        if not ldap_auth(credentials.username, credentials.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return credentials.username

    ldap_protection = Depends(_check_ldap_auth)
    return ldap_protection


    # Example protected route using the dependency
    #@app.get("/protected")
    #async def protected_route(username: str = Depends(check_ldap_auth)):
    #    return {"message": f"Hello, {username}! You have access to this protected route."}
