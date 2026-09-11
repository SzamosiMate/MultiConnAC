from __future__ import annotations

import pytest

from multiconn_archicad.models.tapir import types as tapir
from multiconn_archicad.utilities import BatchResult, BatchResult2D, BatchRun


def error(code: int = 1):
    return tapir.ErrorItem(error=tapir.Error(code=code, message="failed"))


def test_one_dimensional_slots_allow_none_and_expose_indices():
    result = BatchResult.from_items([None, error()])
    assert result.successes == (None,)
    assert result.success_indices == (0,)
    assert result.failure_indices == (1,)
    assert [(index, item.code) for index, item in result.iter_errors()] == [(1, 1)]


@pytest.mark.parametrize("item", [error(), tapir.Error(code=2, message="direct")])
def test_error_normalization_preserves_typed_api_error_identity(item):
    result = BatchResult.from_items([item])
    assert result.slots[0].error.error is (item.error if isinstance(item, tapir.ErrorItem) else item)


def test_one_dimensional_map_skips_error_and_propagates_callback_exception():
    result = BatchResult.from_items(["ok", error()])
    assert result.map(str.upper).successes == ("OK",)
    with pytest.raises(ZeroDivisionError):
        BatchResult.from_items(["ok"]).map(lambda _: 1 / 0)


def test_matrix_retains_ragged_lengths_and_whole_row_error_coordinate():
    result = BatchResult2D.from_rows([["a"], error()], row_lengths=[1, 3])
    assert result.row_lengths == (1, 3)
    assert list(result.iter_errors())[0][0] == (1, None)
    with pytest.raises(ValueError):
        result.flatten()
    assert result.flatten(skip_errors=True) == (("a",), ((0, 0),))


def test_matrix_supports_empty_matrix_empty_rows_and_cell_errors():
    assert BatchResult2D.from_rows([], row_lengths=[]).items == ()
    result = BatchResult2D.from_rows([[], [error(), "ok"]], row_lengths=[0, 2])
    assert list(result.iter_errors())[0][0] == (1, 0)
    assert tuple(result.iter_successes()) == (((1, 1), "ok"),)
    mixed = BatchResult2D.from_rows([[error()], error(2)], row_lengths=[1, 4])
    assert [coordinate for coordinate, _ in mixed.iter_errors()] == [(0, 0), (1, None)]


def test_matrix_map_and_flatten_are_success_only_and_row_major():
    result = BatchResult2D.from_rows([["a", error()], ["b"]], row_lengths=[2, 1])
    mapped = result.map(str.upper)
    flat, coordinates = mapped.flatten()
    assert flat.successes == ("A", "B")
    assert flat.failure_indices == (1,)
    assert coordinates == ((0, 0), (0, 1), (1, 0))
    with pytest.raises(ZeroDivisionError):
        BatchResult2D.from_rows([["a"]], row_lengths=[1]).map(lambda _: 1 / 0)


def test_batch_run_records_one_dimensional_errors_and_preserves_repeated_step_names():
    run = BatchRun(["a", "b"])
    first = BatchResult.from_items(["ok", error()])
    assert run.record("write", first) is first
    run.record("write", BatchResult.from_items(["ok", error(2)]), item_indices=[1, 0])
    assert run.failed_indices == (0, 1)
    assert {failure.step.index for outcome in run.outcomes for failure in outcome.failures} == {0, 1}


def test_batch_run_record_validation_is_atomic_and_abort_keeps_clean_items_incomplete():
    run = BatchRun(["a", "b"])
    with pytest.raises(ValueError):
        run.record("short", BatchResult.from_items([error()]))
    assert run.steps == ()
    run.abort(RuntimeError("fatal"))
    assert isinstance(run.fatal_error, RuntimeError)
    assert run.incomplete_indices == (0, 1)
    assert run.status_counts == {"total": 2, "failed": 0, "succeeded": 0, "incomplete": 2}
    with pytest.raises(RuntimeError):
        run.finish()


def test_batch_run_2d_details_and_multiple_failures_are_ordered_per_outcome():
    run = BatchRun(["first", "second"])
    matrix = BatchResult2D.from_rows([[error(1), error(2)], ["ok"]], row_lengths=[2, 1])
    run.record("matrix", matrix, item_indices=[1, 0], details=["row-0", "row-1"])
    failures = run.outcomes[1].failures
    assert [failure.error.code for failure in failures] == [1, 2]
    assert [failure.source_coordinate for failure in failures] == [(0, 0), (0, 1)]
    assert all(failure.detail == "row-0" for failure in failures)


def test_finish_marks_clean_success_and_empty_run_is_clean():
    assert BatchRun([]).finish() == ()
    run = BatchRun(["only"])
    run.record("read", BatchResult.from_items(["ok"]))
    assert run.finish()[0].succeeded
    with pytest.raises(RuntimeError):
        run.record("retry", BatchResult.from_items(["ok"]))


def test_run_repeated_targets_and_invalid_arguments_are_atomic():
    run = BatchRun(["a", "b"])
    run.record("repeat", BatchResult.from_items([error(), error(2)]), item_indices=[1, 1])
    assert [failure.error.code for failure in run.outcomes[1].failures] == [1, 2]
    before = run.steps
    with pytest.raises(IndexError):
        run.record("bad", BatchResult.from_items(["a", "b"]), item_indices=[0, 2])
    with pytest.raises(ValueError):
        run.record("bad", BatchResult.from_items(["a", "b"]), details=["only one"])
    assert run.steps == before


def test_run_finish_and_abort_statuses_and_separate_retry():
    run = BatchRun(["a", "b"])
    run.record("write", BatchResult.from_items([error(), "ok"]))
    assert [outcome.status for outcome in run.finish()] == ["failed", "succeeded"]
    aborted = BatchRun(["a", "b"])
    aborted.record("write", BatchResult.from_items([error(), "ok"]))
    assert [outcome.status for outcome in aborted.abort(RuntimeError("fatal"))] == ["failed", "incomplete"]
    with pytest.raises(RuntimeError):
        aborted.abort(RuntimeError("again"))
    retry = BatchRun(["a"])
    assert retry.finish()[0].succeeded
