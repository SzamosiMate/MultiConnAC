"""Explicit, immutable containers for partial API batch failures."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Iterator, Literal, TypeAlias, TypeVar, cast, overload

from multiconn_archicad.errors import BatchOperationError
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir

T = TypeVar("T")
U = TypeVar("U")
ErrorType: TypeAlias = tapir.Error | official.Error
ValueCoordinate: TypeAlias = tuple[int, int]
ErrorCoordinate: TypeAlias = tuple[int, int | None]
_MISSING = object()
ERROR_CONTAINER_MODELS = (
    tapir.FailedExecutionResult,
    tapir.ErrorItem,
    official.FailedExecutionResult,
    official.ErrorItem,
)


def extract_error(item: Any) -> ErrorType | None:
    if isinstance(item, ERROR_CONTAINER_MODELS):
        return item.error
    return item if isinstance(item, (tapir.Error, official.Error)) else None


@dataclass(frozen=True, slots=True)
class BatchError:
    error: ErrorType

    @property
    def code(self) -> int | str:
        return self.error.code

    @property
    def message(self) -> str:
        return self.error.message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def normalize_error(item: Any) -> BatchError | None:
    error = extract_error(item)
    return BatchError(error) if error is not None else None


@dataclass(frozen=True, slots=True)
class BatchSlot(Generic[T]):
    """A slot has either a value or a normalized API error, never both."""

    value: T | object = _MISSING
    error: BatchError | None = None

    def __post_init__(self) -> None:
        if (self.value is _MISSING) == (self.error is None):
            raise ValueError("A BatchSlot must contain exactly one of value or error.")

    @property
    def is_success(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class BatchResult(Generic[T]):
    """An immutable one-dimensional result with integer-indexed slots."""

    slots: tuple[BatchSlot[T], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", tuple(self.slots))

    @classmethod
    def from_items(cls, raw_items: Sequence[Any], *, accessor: Callable[[Any], T] | None = None) -> BatchResult[T]:
        slots: list[BatchSlot[T]] = []
        for index, item in enumerate(raw_items):
            failure = normalize_error(item)
            slots.append(BatchSlot(error=failure) if failure else BatchSlot(value=accessor(item) if accessor else item))
        return cls(tuple(slots))

    @property
    def items(self) -> tuple[T | BatchError, ...]:
        return tuple(slot.error if slot.error else cast(T, slot.value) for slot in self.slots)

    @property
    def errors(self) -> tuple[BatchError, ...]:
        return tuple(slot.error for slot in self.slots if slot.error is not None)

    @property
    def all_errors(self) -> tuple[BatchError, ...]:
        return self.errors

    @property
    def successes(self) -> tuple[T, ...]:
        return tuple(cast(T, slot.value) for slot in self.slots if slot.error is None)

    def iter_successes(self) -> Iterator[tuple[int, T]]:
        for index, slot in enumerate(self.slots):
            if slot.error is None:
                yield index, cast(T, slot.value)

    def iter_errors(self) -> Iterator[tuple[int, BatchError]]:
        for index, slot in enumerate(self.slots):
            if slot.error is not None:
                yield index, slot.error

    @property
    def success_indices(self) -> tuple[int, ...]:
        return tuple(index for index, _ in self.iter_successes())

    @property
    def failure_indices(self) -> tuple[int, ...]:
        return tuple(index for index, _ in self.iter_errors())

    @property
    def has_errors(self) -> bool:
        return any(slot.error is not None for slot in self.slots)

    @property
    def is_all_success(self) -> bool:
        return not self.has_errors

    @property
    def total_errors(self) -> int:
        return len(self.errors)

    def map(self, fn: Callable[[T], U]) -> BatchResult[U]:
        """Maps successes only; callback exceptions deliberately propagate."""
        return BatchResult(
            tuple(
                BatchSlot(value=fn(cast(T, slot.value))) if slot.error is None else BatchSlot(error=slot.error)
                for slot in self.slots
            )
        )

    def raise_for_errors(self, operation_name: str = "Batch operation") -> None:
        if self.has_errors:
            lines = "\n".join(f"  - [{index}]: {error}" for index, error in self.iter_errors())
            raise BatchOperationError(
                f"{operation_name} failed with {self.total_errors} error(s):\n{lines}", result=self
            )


@dataclass(frozen=True, slots=True)
class BatchResult2D(Generic[T]):
    """A ragged 2D result. A whole-row API error retains its requested row length."""

    rows: tuple[tuple[BatchSlot[T], ...], ...]
    row_lengths: tuple[int, ...]
    row_errors: tuple[BatchError | None, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(tuple(row) for row in self.rows))
        object.__setattr__(self, "row_lengths", tuple(self.row_lengths))
        object.__setattr__(self, "row_errors", tuple(self.row_errors))
        if len(self.rows) != len(self.row_lengths):
            raise ValueError("rows and row_lengths must have the same length.")
        if not self.row_errors:
            object.__setattr__(self, "row_errors", (None,) * len(self.rows))
        if len(self.row_errors) != len(self.rows):
            raise ValueError("row_errors and rows must have the same length.")
        for row_index, (row, length, row_error) in enumerate(zip(self.rows, self.row_lengths, self.row_errors)):
            if length < 0:
                raise ValueError("row lengths must be non-negative.")
            if row_error is None and len(row) != length:
                raise ValueError("A successful row must contain exactly row_length slots.")
            if row_error and row:
                raise ValueError("A failed row cannot contain cell slots.")

    @classmethod
    def from_rows(
        cls,
        raw_rows: Sequence[Any],
        *,
        row_lengths: Sequence[int] | None = None,
        accessor: Callable[[Any], T] | None = None,
    ) -> BatchResult2D[T]:
        if row_lengths is None:
            row_lengths = tuple(
                len(row) if isinstance(row, Sequence) and not isinstance(row, (str, bytes)) else 0 for row in raw_rows
            )
        if len(raw_rows) != len(row_lengths):
            raise ValueError("raw_rows and row_lengths must have the same length.")
        rows: list[tuple[BatchSlot[T], ...]] = []
        row_errors: list[BatchError | None] = []
        for row_index, (raw_row, expected_length) in enumerate(zip(raw_rows, row_lengths)):
            row_failure = normalize_error(raw_row)
            if row_failure:
                rows.append(())
                row_errors.append(row_failure)
                continue
            if not isinstance(raw_row, Sequence) or isinstance(raw_row, (str, bytes)):
                raise TypeError(f"Row {row_index} must be a sequence or a typed API error.")
            if len(raw_row) != expected_length:
                raise ValueError(
                    f"Row {row_index} length ({len(raw_row)}) does not match supplied length ({expected_length})."
                )
            row: list[BatchSlot[T]] = []
            for cell_index, item in enumerate(raw_row):
                failure = normalize_error(item)
                row.append(
                    BatchSlot(error=failure) if failure else BatchSlot(value=accessor(item) if accessor else item)
                )
            rows.append(tuple(row))
            row_errors.append(None)
        return cls(tuple(rows), tuple(row_lengths), tuple(row_errors))

    @property
    def has_errors(self) -> bool:
        return any(error is not None for error in self.row_errors) or any(
            slot.error is not None for row in self.rows for slot in row
        )

    @property
    def is_all_success(self) -> bool:
        return not self.has_errors

    def iter_successes(self) -> Iterator[tuple[ValueCoordinate, T]]:
        for row_index, row in enumerate(self.rows):
            for cell_index, slot in enumerate(row):
                if slot.error is None:
                    yield (row_index, cell_index), cast(T, slot.value)

    def iter_errors(self) -> Iterator[tuple[ErrorCoordinate, BatchError]]:
        for row_index, row in enumerate(self.rows):
            row_error = self.row_errors[row_index]
            if row_error is not None:
                yield (row_index, None), row_error
                continue
            for cell_index, slot in enumerate(row):
                if slot.error is not None:
                    yield (row_index, cell_index), slot.error

    @property
    def errors(self) -> tuple[BatchError, ...]:
        return tuple(error for _, error in self.iter_errors())

    @property
    def all_errors(self) -> tuple[BatchError, ...]:
        return self.errors

    @property
    def total_errors(self) -> int:
        return len(self.errors)

    @property
    def items(self) -> tuple[tuple[T | BatchError, ...], ...]:
        return tuple(tuple(slot.error if slot.error else cast(T, slot.value) for slot in row) for row in self.rows)

    def map(self, fn: Callable[[T], U]) -> BatchResult2D[U]:
        return BatchResult2D(
            tuple(
                tuple(
                    BatchSlot(value=fn(cast(T, slot.value))) if slot.error is None else BatchSlot(error=slot.error)
                    for slot in row
                )
                for row in self.rows
            ),
            self.row_lengths,
            self.row_errors,
        )

    @overload
    def flatten(self, *, skip_errors: Literal[False] = False) -> tuple[BatchResult[T], tuple[ValueCoordinate, ...]]: ...

    @overload
    def flatten(self, *, skip_errors: Literal[True]) -> tuple[tuple[T, ...], tuple[ValueCoordinate, ...]]: ...

    def flatten(
        self, *, skip_errors: bool = False
    ) -> tuple[BatchResult[T], tuple[ValueCoordinate, ...]] | tuple[tuple[T, ...], tuple[ValueCoordinate, ...]]:
        if any(error is not None for error in self.row_errors) and not skip_errors:
            raise ValueError("Cannot flatten a matrix containing whole-row errors; pass skip_errors=True.")
        flattened: list[BatchSlot[T]] = []
        coordinates: list[ValueCoordinate] = []
        for row_index, row in enumerate(self.rows):
            for cell_index, slot in enumerate(row):
                coordinate = (row_index, cell_index)
                if slot.error is None:
                    flattened.append(BatchSlot(value=slot.value))
                    coordinates.append(coordinate)
                elif not skip_errors:
                    flattened.append(BatchSlot(error=slot.error))
                    coordinates.append(coordinate)
        if skip_errors:
            return tuple(cast(T, slot.value) for slot in flattened), tuple(coordinates)
        return BatchResult(tuple(flattened)), tuple(coordinates)

    def raise_for_errors(self, operation_name: str = "Batch operation") -> None:
        if self.has_errors:
            lines = "\n".join(
                f"  - [{', '.join(map(str, coordinate))}]: {error}" for coordinate, error in self.iter_errors()
            )
            raise BatchOperationError(
                f"{operation_name} failed with {self.total_errors} error(s):\n{lines}", result=self
            )
