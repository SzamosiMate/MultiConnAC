"""Public utility and batch-result classes."""

from multiconn_archicad.errors import BatchOperationError

from .api import Utilities
from .batch_run import (
    BatchFailure,
    BatchOutcome,
    BatchReport,
    BatchResultType,
    BatchRun,
    BatchStatus,
    BatchStep,
)
from .results import BatchError, BatchResult, BatchResult2D

__all__ = [
    "Utilities",
    "BatchResult",
    "BatchResult2D",
    "BatchError",
    "BatchOperationError",
    "BatchRun",
    "BatchStep",
    "BatchFailure",
    "BatchOutcome",
    "BatchReport",
    "BatchStatus",
    "BatchResultType",
]
