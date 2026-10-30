"""pyminleon exception hierarchy."""


class MinleonError(Exception):
    """Base class for every pyminleon error."""


class ConfigError(MinleonError, ValueError):
    """Invalid host, port, timeout, or call argument."""


class ControllerError(MinleonError):
    """A controller could not be reached, timed out, answered with a non-200 status, or sent something unusable."""
