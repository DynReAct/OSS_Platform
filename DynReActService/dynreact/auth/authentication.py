from fastapi.params import Depends

from dynreact.app_config import DynReActSrvConfig


def fastapi_authentication(config: DynReActSrvConfig) -> Depends|None:
    username = None
    if config.auth_method == "ldap":
        from dynreact.auth.ldap_auth import ldap_protection
        username = ldap_protection
    elif config.auth_method == "ldap_simple":
        from dynreact.auth.ldap_auth_simple import ldap_simple_protection
        username = ldap_simple_protection
    elif config.auth_method == "dummy":
        from dynreact.auth.dummy_auth import dummy_protection
        username = dummy_protection
    return username


def authenticate(config: DynReActSrvConfig, user: str, password: str) -> bool:
    if config.auth_method is None:
        return False
    auth_method = None
    if config.auth_method == "ldap":
        from dynreact.auth.ldap_auth import ldap_auth
        auth_method = ldap_auth
    elif config.auth_method == "ldap_simple":
        from dynreact.auth.ldap_auth_simple import ldap_auth_simple
        auth_method = ldap_auth_simple
    elif config.auth_method == "dummy":
        from dynreact.auth.dummy_auth import dummy_auth
        auth_method = dummy_auth
    return auth_method(user, password)


def dash_authenticated(config: DynReActSrvConfig) -> bool:
    if config.auth_method is None:
        return True
    from flask_login import current_user
    return current_user.is_authenticated

