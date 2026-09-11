"""Outcome tracking for multi-step batch workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeAlias, TypeVar, cast

from .results import BatchError, BatchResult, BatchResult2D

T = TypeVar("T")
BatchResultType: TypeAlias = BatchResult[Any] | BatchResult2D[Any]
RecordedResult = TypeVar("RecordedResult", bound=BatchResultType)


class BatchStatus(str, Enum):
    INCOMPLETE = "incomplete"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


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
    status: BatchStatus

    @property
    def failed(self) -> bool:
        return self.status is BatchStatus.FAILED

    @property
    def succeeded(self) -> bool:
        return self.status is BatchStatus.SUCCEEDED

    @property
    def incomplete(self) -> bool:
        return self.status is BatchStatus.INCOMPLETE


@dataclass(frozen=True, slots=True)
class BatchReport(Generic[T]):
    """A complete, immutable snapshot of a batch workflow."""

    outcomes: tuple[BatchOutcome[T], ...]
    steps: tuple[BatchStep[Any], ...]
    status: BatchStatus
    fatal_error: Exception | None = None

    @property
    def failed_indices(self) -> tuple[int, ...]:
        return tuple(outcome.index for outcome in self.outcomes if outcome.failed)

    @property
    def incomplete_indices(self) -> tuple[int, ...]:
        return tuple(outcome.index for outcome in self.outcomes if outcome.incomplete)

    @property
    def status_counts(self) -> Mapping[str, int]:
        return {
            "total": len(self.outcomes),
            "failed": sum(outcome.failed for outcome in self.outcomes),
            "succeeded": sum(outcome.succeeded for outcome in self.outcomes),
            "incomplete": sum(outcome.incomplete for outcome in self.outcomes),
        }


@dataclass(slots=True)
class BatchRun(Generic[T]):
    """Accumulate failures against the original input without losing repeats."""

    original_items: Sequence[T]
    _steps: list[BatchStep[Any]] = field(default_factory=list, init=False, repr=False)
    _failures: list[list[BatchFailure]] = field(default_factory=list, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _aborted: bool = field(default=False, init=False, repr=False)
    _fatal_error: Exception | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.original_items = tuple(self.original_items)
        self._failures = [[] for _ in self.original_items]

    @property
    def steps(self) -> tuple[BatchStep[Any], ...]:
        return tuple(self._steps)

    @property
    def fatal_error(self) -> Exception | None:
        return self._fatal_error

    @property
    def report(self) -> BatchReport[T]:
        """Return an immutable snapshot of the current workflow state."""
        return self._build_report()

    @property
    def outcomes(self) -> tuple[BatchOutcome[T], ...]:
        values: list[BatchOutcome[T]] = []
        for index, item in enumerate(self.original_items):
            status: BatchStatus
            if self._failures[index]:
                status = BatchStatus.FAILED
            elif self._closed and not self._aborted:
                status = BatchStatus.SUCCEEDED
            else:
                status = BatchStatus.INCOMPLETE
            values.append(BatchOutcome(item, index, tuple(self._failures[index]), status))
        return tuple(values)

    def _build_report(self) -> BatchReport[T]:
        outcomes = self.outcomes
        if self._aborted or any(outcome.failed for outcome in outcomes):
            status = BatchStatus.FAILED
        elif self._closed:
            status = BatchStatus.SUCCEEDED
        else:
            status = BatchStatus.INCOMPLETE
        return BatchReport(outcomes, self.steps, status, self._fatal_error)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("This BatchRun is closed.")

    def record(
        self,
        name: str,
        result: RecordedResult,
        *,
        item_indices: Sequence[int] | None = None,
        details: Sequence[Any] | None = None,
    ) -> RecordedResult:
        """Record a step atomically and return the original result object."""
        indices, extra = self._validate_record_inputs(result, item_indices, details)

        step: BatchStep[Any] = BatchStep(name, len(self._steps), result, indices, extra)
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

    def _validate_record_inputs(
        self,
        result: BatchResultType,
        item_indices: Sequence[int] | None,
        details: Sequence[Any] | None,
    ) -> tuple[tuple[int, ...], tuple[Any, ...]]:
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
        return indices, extra

    def finish(self) -> BatchReport[T]:
        self._ensure_open()
        self._closed = True
        return self.report

    def abort(self, exception: Exception) -> BatchReport[T]:
        self._ensure_open()
        self._closed = True
        self._aborted = True
        self._fatal_error = exception
        return self.report
