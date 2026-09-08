# Base Exception
from __future__ import annotations

from typing import Any

from multiconn_archicad.utilities.results import BatchResult


class MulticonnArchicadError(Exception):
    """Base class for all custom exceptions in the multiconn_archicad package."""

    pass


# --- Errors that happen during communication with the API ---


class APIErrorBase(MulticonnArchicadError):
    """
    Base class for errors during API communication or reported by the API.
    Catch this exception for unified handling of all API-related issues.
    """

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code: int | None = code
        self.message: str = message

    def __str__(self):
        return f"error: {{code={self.code}, message='{self.message}}}'"

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.code}, message={self.message}>"

    def to_dict(self) -> dict[str, str]:
        return {"code": str(self.code), "message": self.message}


class RequestError(APIErrorBase):
    """Raised for errors originating from Network/HTTP/Parsing"""

    pass


class APIConnectionError(RequestError):
    """Raised for errors establishing a connection to the ArchiCAD API."""

    pass


class HeaderUnassignedError(RequestError, AttributeError):
    """Raised when a command is called on an unassigned ConnHeader"""

    pass


class CommandTimeoutError(RequestError, TimeoutError):
    """Raised when a command request to the ArchiCAD API times out."""

    pass


class InvalidResponseFormatError(RequestError):
    """Raised when the API response cannot be parsed as valid JSON."""

    pass


class ArchicadAPIError(APIErrorBase):
    """Raised when the ArchiCAD API or the Tapir Add-On indicates a failure in the response body."""

    pass


class StandardAPIError(ArchicadAPIError):
    """Raised when the ArchiCAD API indicates a failure in the response body."""

    pass


class StandardCommandUnavailable(StandardAPIError):
    """Raised when the ArchicadAPI receives an unknown command"""
    def __init__(self, message: str):
        super().__init__(message)
        self.code: int = 2002
        self.message: str = message


class AddOnCommandUnavailable(StandardAPIError):
    """Raised when the ArchicadAPI receives an unknown Add-on command"""
    def __init__(self, message: str):
        super().__init__(message)
        self.code: int = 4010
        self.message: str = message


class TapirCommandError(ArchicadAPIError):
    """Raised when a Tapir Add-On command reports a failure in its response."""

    pass


# --- Errors originating from Library Logic ---


class ProjectAlreadyOpenError(MulticonnArchicadError):
    """Raised when attempting to open a project that is already open."""

    pass


class ProjectNotFoundError(MulticonnArchicadError):
    """Raised when a specified project file cannot be found."""

    pass


class NotFullyInitializedError(MulticonnArchicadError):
    """Raised when an operation is attempted on an object not fully initialized."""

    pass


class BatchOperationError(MulticonnArchicadError):
    """Raised by fail-fast utility functions when one or more batch items fail."""

    def __init__(self, message: str, result: BatchResult[Any]):
        super().__init__(message)
        self.result = result
