class PermissionManager:

    def is_logged_in(self) -> bool:
        """
        Check if a user is associated with the current context, e.g., a user logged-into the web application.
        :return:
        """
        return False

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
        return False

