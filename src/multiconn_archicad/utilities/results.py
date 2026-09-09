from __future__ import annotations

from enum import Enum
from pydantic import BaseModel
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

from multiconn_archicad import BatchOperationError, UnsupportedResultNode
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
ErrorContainers = tapir.FailedExecutionResult | tapir.ErrorItem | official.FailedExecutionResult | official.ErrorItem

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


_LEAF_TYPES = (str, int, float, bool, bytes, UUID, Enum)


def find_errors(node: Any, path: str = "root", indices: tuple[int, ...] = ()) -> list[BatchError]:
    err = extract_error(node)
    if err is not None:
        return [BatchError(path=path, indices=indices, error=err)]

    if node is None or isinstance(node, _LEAF_TYPES):
        return []

    errors: list[BatchError] = []
    if isinstance(node, (list, tuple)):
        for i, child in enumerate(node):
            errors.extend(find_errors(child, f"{path}[{i}]", indices + (i,)))
    elif isinstance(node, BaseModel):
        for field_name, val in node:
            if val is not None:
                errors.extend(find_errors(val, f"{path}.{field_name}", indices))
    else:
        raise UnsupportedResultNode(
            f"find_errors hit unsupported type {type(node).__name__!r} at path '{path}'; "
            "expected a Pydantic model, list/tuple or a leaf primitive."
        )
    return errors


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

    @property
    def success_indices(self) -> tuple[int, ...]:
        """Returns the tuple of indices that had zero errors."""
        return tuple(idx for idx in range(len(self.items)) if idx not in self.errors)

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

    def map(
            self,
            fn: Callable[[T], U],
            *,
            root_key: str = "map",
            catch_calc_errors: bool = True,
    ) -> BatchResult[U]:
        """Transforms batch items with pipeline error awareness.

        - If fn(item) raises AttributeError/KeyError/IndexError on a dirty item,
          the underlying API error is promoted to that slot.
        - If fn(item) succeeds, the new value is inspected: if clean, zombie errors
          from unselected branches are cleared.
        - If catch_calc_errors is True, computation errors (ZeroDivisionError, ValueError,
          etc.) are captured into BatchError rather than crashing the batch.
        """
        new_items: list[U | ErrorContainers] = []
        new_errors: dict[int, tuple[BatchError, ...]] = {}

        for idx, item in enumerate(self.items):
            # 1. If this slot is already a raw root-level error container, pass it through
            if extract_error(item) is not None:
                new_items.append(item)
                if idx in self.errors:
                    new_errors[idx] = self.errors[idx]
                continue

            # 2. Attempt the transformation
            try:
                val = fn(item)
            except (AttributeError, KeyError, IndexError, TypeError) as exc:
                # Did fn navigate into a known broken branch?
                if idx in self.errors:
                    # Match the error from the item's error list, or take the primary error
                    promoted_err = self._resolve_promoted_error(idx, exc)
                    new_items.append(promoted_err)
                    new_errors[idx] = self.errors[idx]
                    continue

                # If idx was not known to be broken, it's a real coding bug in fn
                if not catch_calc_errors:
                    raise
                val = self._create_calc_error(idx, root_key, exc, new_errors)
                new_items.append(val)
                continue
            except Exception as exc:
                # Catch computational errors (e.g. ZeroDivisionError, ValueError)
                if not catch_calc_errors:
                    raise
                val = self._create_calc_error(idx, root_key, exc, new_errors)
                new_items.append(val)
                continue

            # 3. fn succeeded: check if the returned value contains nested errors
            val_errors = find_errors(val, path=f"{root_key}[{idx}]", indices=(idx,))
            if val_errors:
                new_errors[idx] = tuple(val_errors)

            new_items.append(val)

        return BatchResult(items=new_items, errors=new_errors)

    def _resolve_promoted_error(self, idx: int, exc: Exception) -> ErrorContainers:
        """Finds the most specific error model for the branch fn attempted to touch."""
        err_list = self.errors[idx]
        # If there's only one error on this item, promote it directly
        target_error = err_list[0].error
        if isinstance(target_error, (tapir.Error, official.Error)):
            return tapir.ErrorItem(error=target_error)
        return target_error

    def _create_calc_error(
            self, idx: int, root_key: str, exc: Exception, errors_dict: dict[int, tuple[BatchError, ...]]
    ) -> tapir.ErrorItem:
        """Packages an unhandled Python transformation exception into a standard BatchError."""
        err_model = tapir.Error(code=500, message=f"{type(exc).__name__}: {exc}")
        batch_err = BatchError(path=f"{root_key}[{idx}]", indices=(idx,), error=err_model)
        errors_dict[idx] = (batch_err,)
        return tapir.ErrorItem(error=err_model)

    def realign(
            self,
            sub_result: BatchResult[U],
            indices: Optional[Sequence[int]] = None,
            *,
            step_name: str = "step",
    ) -> BatchResult[T | U]:
        """Slices a sub-batch result back into the master coordinate space.

        - Preserves previous errors and unselected items for skipped indices.
        - Updates sub-batch errors to point to master coordinates.
        - If `indices` is omitted, defaults to `self.success_indices`.
        """
        # 1. Determine and validate the index map
        target_indices = tuple(indices) if indices is not None else self.success_indices

        if len(target_indices) != len(sub_result.items):
            raise ValueError(
                f"Sub-batch length ({len(sub_result.items)}) does not match "
                f"target indices length ({len(target_indices)})."
            )

        # 2. Clone master items and errors
        new_items: list[T | U | ErrorContainers] = list(self.items)
        new_errors: dict[int, list[BatchError]] = {k: list(v) for k, v in self.errors.items()}

        # 3. Scatter items and re-index errors
        for sub_idx, master_idx in enumerate(target_indices):
            if master_idx < 0 or master_idx >= len(self.items):
                raise IndexError(f"Master index {master_idx} is out of bounds for batch size {len(self.items)}.")

            # Overwrite master item with sub-batch result
            new_items[master_idx] = sub_result.items[sub_idx]

            # If the sub-batch had errors on this item, re-index them to master space
            if sub_idx in sub_result.errors:
                for sub_err in sub_result.errors[sub_idx]:
                    reindexed_err = BatchError(
                        path=f"{step_name}[{master_idx}]",
                        indices=(master_idx,) + sub_err.indices[1:],
                        error=sub_err.error,
                    )
                    new_errors.setdefault(master_idx, []).append(reindexed_err)

        frozen_errors = {k: tuple(v) for k, v in new_errors.items()}
        return BatchResult(items=new_items, errors=frozen_errors)

    def zip(self, other: BatchResult[U]) -> BatchResult[tuple[T | ErrorContainers, U | ErrorContainers]]:
        """Joins two parallel branches of the same master batch.

        - Pairs items into tuples: `(item_a, item_b)`.
        - Unions errors from both branches, deduplicating shared ancestor errors.
        - `success_indices` automatically becomes the intersection (items clean in both).
        """
        if len(self.items) != len(other.items):
            raise ValueError(
                f"Cannot zip BatchResult of length {len(self.items)} with length {len(other.items)}. "
                "Both branches must be realigned to the same master size."
            )

        # 1. Pair items
        zipped_items = list(zip(self.items, other.items))

        # 2. Union and deduplicate errors across both branches
        all_err_indices = set(self.errors.keys()) | set(other.errors.keys())
        merged_errors: dict[int, list[BatchError]] = {}

        for idx in all_err_indices:
            errs_self = self.errors.get(idx, ())
            errs_other = other.errors.get(idx, ())

            # Deduplicate by error identity and path to prevent common
            # parent errors from being duplicated
            seen = set()
            combined: list[BatchError] = []
            for err in errs_self + errs_other:
                key = (err.path, err.code, err.message)
                if key not in seen:
                    seen.add(key)
                    combined.append(err)

            merged_errors[idx] = combined

        return BatchResult(
            items=zipped_items,
            errors={k: tuple(v) for k, v in merged_errors.items()}
        )