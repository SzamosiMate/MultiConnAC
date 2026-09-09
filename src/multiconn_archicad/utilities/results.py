from __future__ import annotations

from enum import Enum
from pydantic import BaseModel
from collections.abc import Callable, Mapping, Sequence, Iterable
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


def _as_error_container(item: Any) -> ErrorContainers:
    """Normalizes an error or container into a typed ErrorContainers model."""
    if isinstance(item, ERROR_CONTAINER_MODELS):
        return item
    err = extract_error(item) or item
    return tapir.ErrorItem(error=err)


def _deduplicate_errors(errors: Iterable[BatchError]) -> tuple[BatchError, ...]:
    """Preserves order while deduplicating errors by coordinates and content."""
    seen: set[tuple[str, tuple[int, ...], int | str, str]] = set()
    unique: list[BatchError] = []
    for err in errors:
        key = (err.path, err.indices, err.code, err.message)
        if key not in seen:
            seen.add(key)
            unique.append(err)
    return tuple(unique)


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

    def map(self, fn: Callable[[T], U], *, root_key: str = "map", catch_calc_errors: bool = True) -> BatchResult[U]:
        """Apply a transformation while isolating errors and preserving 1:1 index alignment.

        Bypasses root error containers, promotes sub-branch errors if touched by `fn`,
        clears unselected zombie errors on clean returns, and absorbs runtime exceptions
        into BatchError instances when enabled.
        """
        new_items: list[U | ErrorContainers] = []
        new_errors: dict[int, tuple[BatchError, ...]] = {}

        for idx, item in enumerate(self.items):
            mapped_item, slot_errors = self._map_slot(idx, item, fn, root_key, catch_calc_errors)
            new_items.append(mapped_item)
            if slot_errors:
                new_errors[idx] = slot_errors

        return BatchResult(items=new_items, errors=new_errors)

    def _map_slot(
        self, idx: int, item: Any, fn: Callable[[T], U], root_key: str, catch_calc_errors: bool
    ) -> tuple[U | ErrorContainers, tuple[BatchError, ...]]:
        if extract_error(item) is not None:
            return item, self._passthrough_slot_errors(idx, item, root_key)
        return self._transform_slot(idx, item, fn, root_key, catch_calc_errors)

    def _passthrough_slot_errors(self, idx: int, item: Any, root_key: str) -> tuple[BatchError, ...]:
        if idx in self.errors:
            return self.errors[idx]
        err = extract_error(item)
        return (BatchError(path=f"{root_key}[{idx}]", indices=(idx,), error=err),)

    def _transform_slot(
        self, idx: int, item: Any, fn: Callable[[T], U], root_key: str, catch_calc_errors: bool
    ) -> tuple[U | ErrorContainers, tuple[BatchError, ...]]:
        try:
            val = fn(item)
        except (AttributeError, KeyError, IndexError, TypeError) as exc:
            promoted = self._resolve_promoted_error(idx, exc)
            if promoted is not None:
                promoted_item, matched_err = promoted
                return promoted_item, (matched_err,)
            if not catch_calc_errors:
                raise
            return self._create_calc_error(idx, root_key, exc)
        except Exception as exc:
            if not catch_calc_errors:
                raise
            return self._create_calc_error(idx, root_key, exc)

        val_errors = tuple(find_errors(val, path=f"{root_key}[{idx}]", indices=(idx,)))
        return val, val_errors

    def _resolve_promoted_error(self, idx: int, exc: Exception) -> Optional[tuple[ErrorContainers, BatchError]]:
        err_list = self.errors.get(idx)
        if not err_list:
            return None

        return (
            self._match_error_by_object(exc, err_list)
            or self._match_error_by_name(exc, err_list)
            or self._match_single_error_by_type(exc, err_list)
        )

    @staticmethod
    def _match_error_by_object(
        exc: Exception, err_list: tuple[BatchError, ...]
    ) -> Optional[tuple[ErrorContainers, BatchError]]:
        exc_obj = getattr(exc, "obj", None)
        if exc_obj is None:
            return None

        target_err = extract_error(exc_obj)
        if target_err is None:
            return None

        for b_err in err_list:
            if b_err.error == target_err:
                return _as_error_container(exc_obj), b_err
        return _as_error_container(exc_obj), err_list[0]

    @staticmethod
    def _match_error_by_name(
        exc: Exception, err_list: tuple[BatchError, ...]
    ) -> Optional[tuple[ErrorContainers, BatchError]]:
        name = getattr(exc, "name", None) or (exc.args[0] if isinstance(exc, KeyError) and exc.args else None)
        if not name:
            return None

        name_str = str(name)
        for b_err in err_list:
            tokens = b_err.path.replace("[", ".").replace("]", "").split(".")
            if name_str in tokens:
                return _as_error_container(b_err.error), b_err
        return None

    @staticmethod
    def _match_single_error_by_type(
        exc: Exception, err_list: tuple[BatchError, ...]
    ) -> Optional[tuple[ErrorContainers, BatchError]]:
        if len(err_list) == 1 and isinstance(exc, (IndexError, TypeError)):
            return _as_error_container(err_list[0].error), err_list[0]
        return None

    @staticmethod
    def _create_calc_error(idx: int, root_key: str, exc: Exception) -> tuple[tapir.ErrorItem, tuple[BatchError, ...]]:
        err_model = tapir.Error(code=500, message=f"{type(exc).__name__}: {exc}")
        batch_err = BatchError(path=f"{root_key}[{idx}]", indices=(idx,), error=err_model)
        return tapir.ErrorItem(error=err_model), (batch_err,)

    def realign(self, sub_result: BatchResult[U], indices: Optional[Sequence[int]] = None, *, step_name: str = "step"
    ) -> BatchResult[T | U]:
        """Scatter sub-batch items and errors back into master coordinate space.

        Preserves unselected master items and prior errors, translates sub-batch error
        paths to master coordinates, and defaults to scattering across `self.success_indices`.
        """
        targets = tuple(indices) if indices is not None else self.success_indices
        self._validate_realign_targets(targets, len(sub_result.items))

        new_items, new_errors = self._scatter_sub_batch(sub_result, targets, step_name)
        return BatchResult(items=new_items, errors=new_errors)

    def _validate_realign_targets(self, targets: tuple[int, ...], sub_batch_len: int) -> None:
        if len(targets) != sub_batch_len:
            raise ValueError(
                f"Sub-batch length ({sub_batch_len}) does not match target indices length ({len(targets)})."
            )
        if len(set(targets)) != len(targets):
            raise ValueError("Target indices must be unique.")
        for idx in targets:
            if idx < 0 or idx >= len(self.items):
                raise IndexError(f"Master index {idx} is out of bounds for batch size {len(self.items)}.")

    def _scatter_sub_batch(
        self, sub_result: BatchResult[U], targets: tuple[int, ...], step_name: str
    ) -> tuple[list[T | U | ErrorContainers], dict[int, tuple[BatchError, ...]]]:
        new_items: list[T | U | ErrorContainers] = list(self.items)
        merged_errors: dict[int, list[BatchError]] = {k: list(v) for k, v in self.errors.items()}

        for sub_idx, master_idx in enumerate(targets):
            new_items[master_idx] = sub_result.items[sub_idx]
            if sub_idx in sub_result.errors:
                reindexed = [
                    self._reindex_batch_error(err, master_idx, step_name) for err in sub_result.errors[sub_idx]
                ]
                merged_errors.setdefault(master_idx, []).extend(reindexed)

        return new_items, {k: tuple(v) for k, v in merged_errors.items()}

    @staticmethod
    def _reindex_batch_error(sub_err: BatchError, master_idx: int, step_name: str) -> BatchError:
        suffix = sub_err.path[sub_err.path.index("]") + 1 :] if "]" in sub_err.path else ""
        return BatchError(
            path=f"{step_name}[{master_idx}]{suffix}",
            indices=(master_idx,) + sub_err.indices[1:],
            error=sub_err.error,
        )

    def zip(self, other: BatchResult[U]) -> BatchResult[tuple[T | ErrorContainers, U | ErrorContainers]]:
        """Pair two parallel branches of the same batch size into 2-tuples.

        Unions and deduplicates errors from both branches, restricting joint success
        indices to items that succeeded cleanly in both tracks.
        """
        self._validate_zip_alignment(other)
        zipped_items = list(zip(self.items, other.items))
        merged_errors = self._merge_branch_errors(other)
        return BatchResult(items=zipped_items, errors=merged_errors)

    def _validate_zip_alignment(self, other: BatchResult[Any]) -> None:
        if len(self.items) != len(other.items):
            raise ValueError(
                f"Cannot zip BatchResult of length {len(self.items)} with length {len(other.items)}. "
                "Both branches must be realigned to the same master size."
            )

    def _merge_branch_errors(self, other: BatchResult[Any]) -> dict[int, tuple[BatchError, ...]]:
        all_indices = sorted(set(self.errors.keys()) | set(other.errors.keys()))
        return {idx: _deduplicate_errors(self.errors.get(idx, ()) + other.errors.get(idx, ())) for idx in all_indices}
