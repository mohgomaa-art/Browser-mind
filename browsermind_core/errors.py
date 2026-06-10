"""Shared exception types for BrowserMind."""


class AuthGateError(RuntimeError):
    """
    Raised by ExplorerPolicy when the page only offers auth affordances and
    no executable affordances are available — meaning the site requires login
    before anything useful can be explored.

    The error message always starts with "auth_required:" so MissionWorker's
    _AUTH_WALL_KEYWORDS check picks it up and marks the mission as paused.
    """
    pass
