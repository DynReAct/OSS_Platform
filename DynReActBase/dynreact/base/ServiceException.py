class ServiceException(Exception):
    """
    Exception used by DynReAct to indicate that a service is not accessible or reports an error.
    """

    def __init__(self, status: int, reason: str|None=None, details: str|None=None):
        """

        Parameters:
            status: 1 = service not available/accessible, 500 = generic error
        """
        self._status = status
        self._reason = reason
        self._details = details

    def __str__(self):
        return f"ServiceException(status={self._status}, reason={self._reason})"

