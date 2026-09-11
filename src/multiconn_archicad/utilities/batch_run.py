"""Outcome tracking for multi-step batch workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar, cast

from .results import BatchError, BatchResult, BatchResult2D

T = TypeVar("T")
R = TypeVar("R", BatchResult[Any], BatchResult2D[Any])


@dataclass(frozen=True, slots=True)
class BatchStep(Generic[T]):
    name: str
    index: int
    result: BatchResult[T] | BatchResult2D[T]
    item_indices: tuple[int, ...]
    details: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class BatchFailure:
    step: BatchStep[Any]
    source_coordinate: int | tuple[int, int | None]
    detail: Any
    error: BatchError

    @property
    def step_ref(self) -> BatchStep[Any]:
        return self.step

    @property
    def step_index(self) -> int:
        return self.step.index

    @property
    def step_name(self) -> str:
        return self.step.name


@dataclass(frozen=True, slots=True)
class BatchOutcome(Generic[T]):
    original_item: T
    index: int
    failures: tuple[BatchFailure, ...]
    status: Literal["failed", "succeeded", "incomplete"]

    @property
    def failed(self) -> bool:
        return self.status == "failed"

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"

    @property
    def incomplete(self) -> bool:
        return self.status == "incomplete"


@dataclass(slots=True)
class BatchRun(Generic[T]):
    """Accumulate failures against the original input without losing repeats."""

    original_items: tuple[T, ...]
    _steps: list[BatchStep[Any]] = field(default_factory=list, init=False, repr=False)
    _failures: list[list[BatchFailure]] = field(default_factory=list, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _aborted: bool = field(default=False, init=False, repr=False)
    _fatal_error: Exception | None = field(default=None, init=False, repr=False)

    def __init__(self, original_items: Sequence[T]):
        self.original_items = tuple(original_items)
        self._steps = []
        self._failures = [[] for _ in self.original_items]
        self._closed = False
        self._aborted = False
        self._fatal_error = None

    @property
    def steps(self) -> tuple[BatchStep[Any], ...]:
        return tuple(self._steps)

    @property
    def fatal_error(self) -> Exception | None:
        return self._fatal_error

    @property
    def outcomes(self) -> tuple[BatchOutcome[T], ...]:
        values: list[BatchOutcome[T]] = []
        for index, item in enumerate(self.original_items):
            status: Literal["failed", "succeeded", "incomplete"]
            if self._failures[index]:
                status = "failed"
            elif self._closed and not self._aborted:
                status = "succeeded"
            else:
                status = "incomplete"
            values.append(BatchOutcome(item, index, tuple(self._failures[index]), status))
        return tuple(values)

    @property
    def failed_indices(self) -> tuple[int, ...]:
        return tuple(item.index for item in self.outcomes if item.failed)

    @property
    def incomplete_indices(self) -> tuple[int, ...]:
        return tuple(item.index for item in self.outcomes if item.incomplete)

    @property
    def status_counts(self) -> Mapping[str, int]:
        outcomes = self.outcomes
        return {
            "total": len(outcomes),
            "failed": sum(item.failed for item in outcomes),
            "succeeded": sum(item.succeeded for item in outcomes),
            "incomplete": sum(item.incomplete for item in outcomes),
        }

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("This BatchRun is closed.")

    def record(
        self,
        name: str,
        result: R,
        *,
        item_indices: Sequence[int] | None = None,
        details: Sequence[Any] | None = None,
    ) -> R:
        """Record a step atomically and return the original result object."""
        self._ensure_open()
        source_count = len(result.slots) if isinstance(result, BatchResult) else len(result.rows)
        if item_indices is None and source_count != len(self.original_items):
            raise ValueError("Default item_indices requires one slot/row per original item.")
        indices = tuple(range(source_count)) if item_indices is None else tuple(item_indices)
        if len(indices) != source_count:
            raise ValueError("item_indices length must match result slots or rows.")
        if any(not isinstance(index, int) or index < 0 or index >= len(self.original_items) for index in indices):
            raise IndexError("item_indices contains an original-item index out of bounds.")
        extra = (None,) * source_count if details is None else tuple(details)
        if len(extra) != source_count:
            raise ValueError("details length must match result slots or rows.")

        step = BatchStep(name, len(self._steps), result, indices, extra)
        staged: list[tuple[int, BatchFailure]] = []
        if isinstance(result, BatchResult):
            for source_index, error in result.iter_errors():
                staged.append((indices[source_index], BatchFailure(step, source_index, extra[source_index], error)))
        else:
            for coordinate, error in result.iter_errors():
                row_index = cast(int, coordinate[0])
                staged.append((indices[row_index], BatchFailure(step, coordinate, extra[row_index], error)))

        self._steps.append(step)
        for target, failure in staged:
            self._failures[target].append(failure)
        return result

    def finish(self) -> tuple[BatchOutcome[T], ...]:
        self._ensure_open()
        self._closed = True
        return self.outcomes

    def abort(self, exception: Exception) -> tuple[BatchOutcome[T], ...]:
        self._ensure_open()
        self._closed = True
        self._aborted = True
        self._fatal_error = exception
        return self.outcomes
