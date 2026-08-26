"""Application-specific exceptions."""


class XPSError(Exception):
    """Base exception for user-facing XPS errors."""


class XPSDataError(XPSError, ValueError):
    """Raised when an imported spectrum is malformed."""


class XPSStorageError(XPSError, OSError):
    """Raised when a project cannot be saved or opened."""
