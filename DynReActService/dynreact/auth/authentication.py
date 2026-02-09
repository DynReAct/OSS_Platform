from typing import Callable

from fastapi.params import Depends

from dynreact.app_config import DynReActSrvConfig
from dynreact.base.PermissionManager import PermissionManager


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


def get_current_user() -> str|None:
    try:
        from flask_login import current_user
        return current_user.get_id()
    except:
        return None


def get_permission_manager(config: DynReActSrvConfig) -> PermissionManager:
    if config.auth_method is None or config.auth_method in ("dummy", "ldap_simple"):
        return _DummyPermissions()
    perm_check = None
    if config.auth_method == "ldap":
        from dynreact.auth.ldap_auth import ldap_has_permission
        perm_check = ldap_has_permission
    else:
        raise Exception(f"Unsupported auth scheme {config.auth_method}")
    return _PermissionManagerImpl(perm_check)


class _DummyPermissions(PermissionManager):

    def is_logged_in(self) -> bool:
        return get_current_user() is not None

    def check_permission(self, permission: str, user: str | None = None) -> bool:
        return True


class _PermissionManagerImpl(PermissionManager):

    def __init__(self, perm_check: Callable[[str, str], bool]):
        self._perm_check = perm_check
        #self._config = config

    def is_logged_in(self) -> bool:
        return get_current_user() is not None

    def check_permission(self, permission: str, user: str|None=None) -> bool:

        """
        Check a permission for a user. If the user can be determined from the context, e.g., as the logged-in user in
        a web request, it need not be specified explicitly.

        Parameters:
            permission:
            user

        Returns:
             true or false
        """
        if user is None:
            user = get_current_user()
            if user is None:
                return False
        return self._perm_check(permission, user)

