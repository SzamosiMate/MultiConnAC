from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Optional, TypeVar

from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir

ERROR_CONTAINER_MODELS = (
    tapir.FailedExecutionResult,
    tapir.ErrorItem,
    official.FailedExecutionResult,
    official.ErrorItem,
)

T = TypeVar("T")
U = TypeVar("U")
ErrorType = tapir.Error | official.Error
ErrorContainers = ERROR_CONTAINER_MODELS

def extract_error(item: Any) -> Optional[ErrorType]:
    """Extract an Archicad API Error instance from typed response items."""
    if isinstance(item, ERROR_CONTAINER_MODELS):
        return item.error
    if isinstance(item, (tapir.Error, official.Error)):
        return item
    return None


@dataclass(frozen=True, slots=True)
class BatchError:
    """An API error paired with its coordinate path in the response tree."""

    path: str
    indices: tuple[int, ...]
    error: ErrorType

    @property
    def code(self) -> int | str:
        return getattr(self.error, "code", "ERR")

    @property
    def message(self) -> str:
        return getattr(self.error, "message", str(self.error))

    def __str__(self) -> str:
        return f"{self.path}: [{self.code}] {self.message}"


def find_errors(node: Any, path: str = "root", indices: tuple[int, ...] = ()) -> list[BatchError]:
    """Recursively walks Pydantic models and sequences to extract all Archicad errors."""
    err = extract_error(node)
    if err is not None:
        return [BatchError(path=path, indices=indices, error=err)]

    errors: list[BatchError] = []
    if isinstance(node, (list, tuple)):
        for i, child in enumerate(node):
            errors.extend(find_errors(child, f"{path}[{i}]", indices + (i,)))
    elif hasattr(node, "__dict__"):
        for field_name, val in node.__dict__.items():
            if not field_name.startswith("_") and val is not None:
                errors.extend(find_errors(val, f"{path}.{field_name}", indices))
    return errors


class BatchOperationError(RuntimeError):
    """Raised by fail-fast utility functions when one or more batch items fail."""

    def __init__(self, message: str, result: BatchResult[Any]):
        super().__init__(message)
        self.result = result


@dataclass(frozen=True, slots=True, repr=False)
class BatchResult(Generic[T]):
    """Immutable batch execution container preserving 1:1 index alignment.

    Guarantees:
    - len(items) == len(input_items)
    - Failed indices contain their raw Error model in `items` and are mapped in `errors[batch_idx]`.
    - Multiple errors occurring on the same batch index are preserved in `errors[batch_idx]`.
    - Truthiness evaluates to True only when all operations succeeded (is_all_success).
    """

    items: Sequence[T | ErrorContainers]
    errors: Mapping[int, tuple[BatchError, ...]] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        """True if one or more operations in the batch failed."""
        return len(self.errors) > 0

    @property
    def is_all_success(self) -> bool:
        """True if every operation in the batch succeeded without errors."""
        return len(self.errors) == 0

    @property
    def total_errors(self) -> int:
        """Total count of all errors across all batch items."""
        return sum(len(err_list) for err_list in self.errors.values())

    @property
    def all_errors(self) -> list[BatchError]:
        """Flat list of all errors across all items."""
        return [err for err_list in self.errors.values() for err in err_list]

    @property
    def successes(self) -> list[T]:
        """Returns only the items that had zero errors anywhere in their evaluation."""
        return [item for idx, item in enumerate(self.items) if idx not in self.errors]

    def _validate_alignment(self, parameters: Sequence[Any]) -> None:
        """Ensures the external parameter sequence aligns 1:1 with the result items."""
        if len(parameters) != len(self.items):
            raise ValueError(f"Parameters length ({len(parameters)}) must match result length ({len(self.items)})")

    def success_mask(self, parameters: Sequence[U], fallback: Optional[U] = None) -> list[U | None]:
        """Aligns `parameters` with batch outcomes, replacing failed indices with `fallback` (default None)."""
        self._validate_alignment(parameters)
        return [p if idx not in self.errors else fallback for idx, p in enumerate(parameters)]

    def failure_mask(self, parameters: Sequence[U], fallback: Optional[U] = None) -> list[U | None]:
        """Aligns `parameters` with batch outcomes, replacing successful indices with `fallback` (default None)."""
        self._validate_alignment(parameters)
        return [p if idx in self.errors else fallback for idx, p in enumerate(parameters)]

    def filter_successful(self, parameters: Sequence[U]) -> list[U]:
        """Filters `parameters`, returning only those whose corresponding batch operation succeeded."""
        self._validate_alignment(parameters)
        return [p for idx, p in enumerate(parameters) if idx not in self.errors]

    def filter_failed(self, parameters: Sequence[U]) -> list[U]:
        """Filters `parameters`, returning only those whose corresponding batch operation failed."""
        self._validate_alignment(parameters)
        return [p for idx, p in enumerate(parameters) if idx in self.errors]

    def raise_for_errors(self, operation_name: str = "Batch operation") -> None:
        """Raises a consolidated BatchOperationError if any operation in the batch failed."""
        if not self.has_errors:
            return
        details = [f"  - {err}" for err in self.all_errors]
        msg = (
            f"{operation_name} failed with {self.total_errors} error(s) "
            f"across {len(self.errors)} item(s):\n" + "\n".join(details)
        )
        raise BatchOperationError(msg, result=self)

    def items_or(self, fallback: U = None) -> list[T | U]:
        """Lazy padded representation: returns items with top-level failures replaced by `fallback`."""
        return [fallback if idx in self.errors else item for idx, item in enumerate(self.items)]

    def __bool__(self) -> bool:
        """Falsy if partial or total batch failure occurred."""
        return self.is_all_success

    def _infer_item_type(self) -> str:
        if not self.items:
            return "empty"
        sample = self.successes[0] if self.successes else None
        if sample is None:
            # Fall back to first non-error item in items
            for idx, it in enumerate(self.items):
                if idx not in self.errors:
                    return type(it).__name__
            return "Unknown"
        return type(sample).__name__

    def __repr__(self) -> str:
        type_name = self._infer_item_type()
        total = len(self.items)
        clean = len(self.successes)
        total_errs = self.total_errors
        return f"BatchResult[{type_name}](total={total}, successes={clean}, errors={total_errs})"

    def __str__(self) -> str:
        type_name = self._infer_item_type()
        total = len(self.items)
        if not self.items:
            return f"BatchResult[{type_name}]: empty"
        if self.is_all_success:
            return f"BatchResult[{type_name}]: All {total} succeeded"
        failed_items = len(self.errors)
        total_errs = self.total_errors
        err_str = (
            f"{total_errs} error(s) across {failed_items} item(s)"
            if total_errs != failed_items
            else f"{total_errs} failed"
        )
        return f"BatchResult[{type_name}]: {len(self.successes)}/{total} succeeded ({err_str})"

    def debug_dump(self) -> dict[str, Any]:
        """Returns the full dictionary of items and errors for debugging."""
        return {
            "items": list(self.items),
            "errors": {
                idx: [
                    {
                        "path": err.path,
                        "indices": err.indices,
                        "code": err.code,
                        "message": err.message,
                    }
                    for err in err_list
                ]
                for idx, err_list in self.errors.items()
            },
            "total_errors": self.total_errors,
        }

    @classmethod
    def from_items(
        cls, raw_items: Sequence[Any], *, accessor: Optional[Callable[[Any], T]] = None, root_key: str = "root"
    ) -> BatchResult[T]:
        """Universal factory for any API response (1D sequences, 2D matrices, trees, or execution masks).

        Automatically traverses nested models to extract all errors, grouping them by the top-level batch index.
        """
        tree_errors = find_errors(raw_items, path=root_key)

        error_map: dict[int, list[BatchError]] = {}
        for err in tree_errors:
            batch_idx = err.indices[0] if err.indices else 0
            error_map.setdefault(batch_idx, []).append(err)

        items: list[T | ErrorContainers] = []
        for idx, raw_item in enumerate(raw_items):
            if idx in error_map and extract_error(raw_item) is not None:
                items.append(raw_item)
            else:
                items.append(accessor(raw_item) if accessor is not None else raw_item)

        frozen_errors = {k: tuple(v) for k, v in error_map.items()}
        return cls(items=items, errors=frozen_errors)