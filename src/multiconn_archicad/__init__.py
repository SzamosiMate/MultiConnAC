from __future__ import annotations

from importlib import import_module
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .basic_types import (
        APIResponseError,
        ArchicadLocation,
        ArchiCadID,
        Port,
        ProductInfo,
        SoloProjectID,
        TapirInfo,
        TeamworkCredentials,
        TeamworkProjectID,
        UntitledProjectID,
    )
    from .conn_header import (
        ConnHeader,
        ProjectIdentityHeader,
        SessionReadyHeader,
        ValidatedHeader,
        has_project_identity,
        is_header_fully_initialized,
        is_id_initialized,
        is_location_initialized,
        is_product_info_initialized,
        is_session_ready,
        is_tapir_session_ready,
    )
    from .core.core_commands import CoreCommands
    from .dialog_handlers import (
        DialogHandlerBase,
        UnhandledDialogError,
        WinDialogHandler,
        win_int_handler_factory,
    )
    from .errors import (
        AddOnCommandUnavailable,
        APIConnectionError,
        APIErrorBase,
        ArchicadAPIError,
        CommandTimeoutError,
        InvalidResponseFormatError,
        MulticonnArchicadError,
        NotFullyInitializedError,
        ProjectAlreadyOpenError,
        ProjectNotFoundError,
        RequestError,
        StandardAPIError,
        StandardCommandUnavailable,
        TapirCommandError,
    )
    from .multi_conn import MultiConn
    from .standard_connection import StandardConnection
    from .unified_api.api import UnifiedApi

__all__ = [
    "MultiConn",
    "ConnHeader",
    "ArchiCadID",
    "APIResponseError",
    "ProductInfo",
    "Port",
    "TapirInfo",
    "StandardConnection",
    "CoreCommands",
    "TeamworkCredentials",
    "DialogHandlerBase",
    "UnhandledDialogError",
    "WinDialogHandler",
    "win_int_handler_factory",
    "TeamworkProjectID",
    "SoloProjectID",
    "UntitledProjectID",
    "ArchicadLocation",
    "MulticonnArchicadError",
    "APIErrorBase",
    "RequestError",
    "ArchicadAPIError",
    "APIConnectionError",
    "CommandTimeoutError",
    "InvalidResponseFormatError",
    "StandardAPIError",
    "StandardCommandUnavailable",
    "TapirCommandError",
    "AddOnCommandUnavailable",
    "ProjectAlreadyOpenError",
    "ProjectNotFoundError",
    "NotFullyInitializedError",
    "ProjectIdentityHeader",
    "SessionReadyHeader",
    "ValidatedHeader",
    "is_location_initialized",
    "is_product_info_initialized",
    "is_id_initialized",
    "has_project_identity",
    "is_session_ready",
    "is_tapir_session_ready",
    "is_header_fully_initialized",
    "UnifiedApi",
]

_LAZY_IMPORTS: dict[str, str] = {
    # .multi_conn
    "MultiConn": ".multi_conn",
    # .conn_header
    "ConnHeader": ".conn_header",
    "ProjectIdentityHeader": ".conn_header",
    "SessionReadyHeader": ".conn_header",
    "ValidatedHeader": ".conn_header",
    "has_project_identity": ".conn_header",
    "is_session_ready": ".conn_header",
    "is_tapir_session_ready": ".conn_header",
    "is_header_fully_initialized": ".conn_header",
    "is_id_initialized": ".conn_header",
    "is_location_initialized": ".conn_header",
    "is_product_info_initialized": ".conn_header",
    # .basic_types
    "ArchiCadID": ".basic_types",
    "TeamworkProjectID": ".basic_types",
    "SoloProjectID": ".basic_types",
    "UntitledProjectID": ".basic_types",
    "TeamworkCredentials": ".basic_types",
    "ProductInfo": ".basic_types",
    "ArchicadLocation": ".basic_types",
    "Port": ".basic_types",
    "APIResponseError": ".basic_types",
    "TapirInfo": ".basic_types",
    # .standard_connection
    "StandardConnection": ".standard_connection",
    # .core.core_commands
    "CoreCommands": ".core.core_commands",
    # .dialog_handlers
    "DialogHandlerBase": ".dialog_handlers",
    "UnhandledDialogError": ".dialog_handlers",
    "WinDialogHandler": ".dialog_handlers",
    "win_int_handler_factory": ".dialog_handlers",
    # .errors
    "MulticonnArchicadError": ".errors",
    "APIErrorBase": ".errors",
    "RequestError": ".errors",
    "APIConnectionError": ".errors",
    "CommandTimeoutError": ".errors",
    "InvalidResponseFormatError": ".errors",
    "ArchicadAPIError": ".errors",
    "StandardAPIError": ".errors",
    "StandardCommandUnavailable": ".errors",
    "TapirCommandError": ".errors",
    "AddOnCommandUnavailable": ".errors",
    "ProjectAlreadyOpenError": ".errors",
    "ProjectNotFoundError": ".errors",
    "NotFullyInitializedError": ".errors",
    # .unified_api.api
    "UnifiedApi": ".unified_api.api",
}


def __getattr__(name: str) -> Any:
    """Lazily load symbols when accessed on the module."""
    if name in _LAZY_IMPORTS:
        submodule = import_module(_LAZY_IMPORTS[name], __name__)
        attr = getattr(submodule, name)
        # Cache the resolved object in module globals so __getattr__ is bypassed next time
        globals()[name] = attr
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Ensure dir(multiconn_archicad) and REPL autocomplete show all public exports."""
    return sorted(list(globals().keys()) + __all__)


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)