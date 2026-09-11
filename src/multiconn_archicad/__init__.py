import logging

from multiconn_archicad.orchestration.multi_conn import MultiConn
from multiconn_archicad.orchestration.conn_header import (
    ConnHeader,
    ProjectIdentityHeader,
    SessionReadyHeader,
    ValidatedHeader,
    has_project_identity,
    is_session_ready,
    is_tapir_session_ready,
    is_header_fully_initialized,
    is_id_initialized,
    is_location_initialized,
    is_product_info_initialized,
)
from multiconn_archicad.orchestration.basic_types import (
    ArchiCadID,
    TeamworkProjectID,
    SoloProjectID,
    UntitledProjectID,
    TeamworkCredentials,
    ProductInfo,
    ArchicadLocation,
    Port,
    APIResponseError,
    TapirInfo,
)
from .clients.standard_connection import StandardConnection
from .clients.core.core_commands import CoreCommands
from multiconn_archicad.orchestration.dialog_handlers import (
    DialogHandlerBase,
    UnhandledDialogError,
    WinDialogHandler,
    win_int_handler_factory,
)
from .errors import (
    MulticonnArchicadError,
    APIErrorBase,
    RequestError,
    APIConnectionError,
    CommandTimeoutError,
    InvalidResponseFormatError,
    ArchicadAPIError,
    StandardAPIError,
    StandardCommandUnavailable,
    TapirCommandError,
    AddOnCommandUnavailable,
    ProjectAlreadyOpenError,
    ProjectNotFoundError,
    NotFullyInitializedError,
    BatchOperationError,
)
from multiconn_archicad.clients.unified_api.api import UnifiedApi


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
    "BatchOperationError",
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


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
