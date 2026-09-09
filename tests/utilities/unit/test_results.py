from __future__ import annotations
import pytest
import uuid
from multiconn_archicad.errors import UnsupportedResultNode
from multiconn_archicad.utilities.results import BatchError, BatchOperationError, BatchResult, extract_error
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir


class TestExtractError:
    def test_extracts_from_tapir_failed_execution_result(self):
        err = tapir.Error(code=404, message="Element not found")
        item = tapir.FailedExecutionResult(error=err)
        assert extract_error(item) == err

    def test_extracts_from_tapir_error_item(self):
        err = tapir.Error(code=500, message="Internal error")
        item = tapir.ErrorItem(error=err)
        assert extract_error(item) == err

    def test_extracts_from_official_failed_execution_result(self):
        err = official.Error(code=400, message="Official execution failure")
        item = official.FailedExecutionResult(error=err)
        assert extract_error(item) == err

    def test_extracts_direct_error_model(self):
        err = tapir.Error(code=404, message="Element not found")
        assert extract_error(err) == err

    def test_returns_none_for_successful_models(self):
        assert extract_error(tapir.SuccessfulExecutionResult()) is None
        assert extract_error(official.SuccessfulExecutionResult()) is None


class TestBatchResultFromItems:
    def test_all_successful_flat(self):
        raw = ["elem_1", "elem_2"]
        result = BatchResult.from_items(raw)

        assert result.is_all_success is True
        assert result.items == ["elem_1", "elem_2"]
        assert result.successes == ["elem_1", "elem_2"]
        assert result.errors == {}
        assert result.total_errors == 0

    def test_partial_failure_preserves_error_models(self):
        err_item = tapir.ErrorItem(error=tapir.Error(code=99, message="Unavailable"))
        raw = [
            tapir.PropertyValue(value="A"),
            err_item,
            tapir.PropertyValue(value="B"),
        ]
        result = BatchResult.from_items(raw, accessor=lambda pv: pv.value)

        assert result.is_all_success is False
        assert result.items == ["A", err_item, "B"]  # Error item is preserved!
        assert result.successes == ["A", "B"]
        assert result.items_or(None) == ["A", None, "B"]  # Fallback accessor works
        assert result.errors[1][0].code == 99
        assert result.errors[1][0].path == "root[1]"

    def test_nested_tree_multiple_errors_on_same_item(self):
        err1 = tapir.ErrorItem(error=tapir.Error(code=2, message="Not applicable"))
        err2 = tapir.ErrorItem(error=tapir.Error(code=500, message="Div by zero"))

        raw = [
            tapir.PropertyValuesArrayItem(
                propertyValues=[
                    tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-01")),
                    err1,
                    err2,
                ]
            ),
            tapir.PropertyValuesArrayItem(
                propertyValues=[
                    tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-02")),
                ]
            ),
        ]

        result = BatchResult.from_items(
            raw,
            accessor=lambda el: [
                getattr(p.propertyValue, "value", None) if hasattr(p, "propertyValue") else p for p in el.propertyValues
            ],
            root_key="elements",
        )

        assert result.is_all_success is False
        assert result.total_errors == 2

        # Verify raw nested error items are preserved in the list
        assert result.items[0] == ["Wall-01", err1, err2]
        assert result.items[1] == ["Wall-02"]

        # Clean successes contains only Element 1
        assert result.successes == [["Wall-02"]]


class TestBatchResultDisplayAndShape:
    def test_str_and_repr_all_success(self):
        result = BatchResult.from_items([["Wall-01"], ["Wall-02"]])
        assert str(result) == "BatchResult[list]: All 2 succeeded"
        assert repr(result) == "BatchResult[list](total=2, successes=2, errors=0)"

    def test_str_and_repr_with_nested_errors(self):
        err1 = tapir.ErrorItem(error=tapir.Error(code=2, message="Fail 1"))
        err2 = tapir.ErrorItem(error=tapir.Error(code=5, message="Fail 2"))
        raw = [
            tapir.PropertyValuesArrayItem(propertyValues=[err1, err2]),
            tapir.PropertyValuesArrayItem(
                propertyValues=[
                    tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="OK")),
                ]
            ),
        ]

        result = BatchResult.from_items(
            raw,
            accessor=lambda el: [
                getattr(p.propertyValue, "value", None) if hasattr(p, "propertyValue") else p for p in el.propertyValues
            ],
            root_key="elements",
        )

        assert str(result) == "BatchResult[list]: 1/2 succeeded (2 error(s) across 1 item(s))"
        assert repr(result) == "BatchResult[list](total=2, successes=1, errors=2)"


class TestDebugDump:
    def test_debug_dump_structure_with_nested_errors(self):
        err = tapir.ErrorItem(error=tapir.Error(code=2, message="Not evaluated"))
        raw = [
            tapir.PropertyValuesArrayItem(
                propertyValues=[
                    tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-01")),
                    err,
                ]
            ),
        ]

        result = BatchResult.from_items(
            raw,
            accessor=lambda el: [
                getattr(p.propertyValue, "value", None) if hasattr(p, "propertyValue") else p for p in el.propertyValues
            ],
            root_key="elements",
        )

        dump = result.debug_dump()
        assert dump["items"] == [["Wall-01", err]]
        assert dump["total_errors"] == 1
        assert 0 in dump["errors"]
        assert dump["errors"][0] == [
            {
                "path": "elements[0].propertyValues[1]",
                "indices": (0, 1),
                "code": 2,
                "message": "Not evaluated",
            }
        ]


class TestMaskingAndFiltering:
    @pytest.fixture
    def sample_batch_result(self):
        err = tapir.FailedExecutionResult(success=False, error=tapir.Error(code=500, message="Locked"))
        raw = [
            tapir.SuccessfulExecutionResult(),
            err,
            tapir.SuccessfulExecutionResult(),
        ]
        return BatchResult.from_items(raw, root_key="executionResults")

    def test_success_mask(self, sample_batch_result):
        params = ["Wall_A", "Wall_B", "Wall_C"]
        masked = sample_batch_result.success_mask(params)
        assert masked == ["Wall_A", None, "Wall_C"]

        masked_custom = sample_batch_result.success_mask(params, fallback="FAILED")
        assert masked_custom == ["Wall_A", "FAILED", "Wall_C"]

    def test_failure_mask(self, sample_batch_result):
        params = ["Wall_A", "Wall_B", "Wall_C"]
        masked = sample_batch_result.failure_mask(params)
        assert masked == [None, "Wall_B", None]

    def test_filter_successful(self, sample_batch_result):
        params = ["Wall_A", "Wall_B", "Wall_C"]
        filtered = sample_batch_result.filter_successful(params)
        assert filtered == ["Wall_A", "Wall_C"]

    def test_filter_failed(self, sample_batch_result):
        params = ["Wall_A", "Wall_B", "Wall_C"]
        failed = sample_batch_result.filter_failed(params)
        assert failed == ["Wall_B"]

    def test_length_mismatch_raises(self, sample_batch_result):
        with pytest.raises(ValueError, match=r"Parameters length \(2\) must match result length \(3\)"):
            sample_batch_result.filter_successful(["Only", "Two"])


class TestRaiseForErrors:
    def test_does_not_raise_when_all_succeed(self):
        result = BatchResult.from_items(["item_1", "item_2"])
        result.raise_for_errors()

    def test_raises_batch_operation_error_on_failure(self):
        err = tapir.ErrorItem(error=tapir.Error(code=404, message="Element deleted"))
        result = BatchResult.from_items(["ok", err], root_key="elements")

        with pytest.raises(BatchOperationError) as exc_info:
            result.raise_for_errors("Element query")

        exc = exc_info.value
        assert exc.result is result
        assert "Element query failed with 1 error(s) across 1 item(s):" in str(exc)
        assert "- elements[1]: [404] Element deleted" in str(exc)


class TestFindErrors:
    def test_raises_unsupported_result_node_for_invalid_types(self):
        with pytest.raises(UnsupportedResultNode, match="hit unsupported type 'set'"):
            BatchResult.from_items([{"not", "supported"}])

    @pytest.mark.parametrize("leaf", ["str", 42, 3.14, True, b"bytes", uuid.uuid4()])
    def test_primitives_produce_no_errors(self, leaf):
        result = BatchResult.from_items([leaf])
        assert result.is_all_success is True
        assert result.total_errors == 0


class TestBatchResultTruthinessAndEmpty:
    def test_truthiness_evaluates_on_success_status(self):
        success_result = BatchResult.from_items(["item1", "item2"])
        assert bool(success_result) is True

        err = tapir.ErrorItem(error=tapir.Error(code=1, message="fail"))
        failure_result = BatchResult.from_items(["item1", err])
        assert bool(failure_result) is False

    def test_empty_batch_result(self):
        result = BatchResult.from_items([])
        assert result.is_all_success is True
        assert result.items == []
        assert result.successes == []
        assert str(result) == "BatchResult[empty]: empty"
        assert repr(result) == "BatchResult[empty](total=0, successes=0, errors=0)"


class TestBatchErrorDetails:
    def test_all_errors_property(self):
        err1 = tapir.ErrorItem(error=tapir.Error(code=1, message="E1"))
        err2 = tapir.ErrorItem(error=tapir.Error(code=2, message="E2"))
        result = BatchResult.from_items([err1, "ok", err2])

        all_errs = result.all_errors
        assert len(all_errs) == 2
        assert [e.code for e in all_errs] == [1, 2]
        assert str(all_errs[0]) == "root[0]: [1] E1"

    def test_error_code_and_message_fallbacks(self):
        class MinimalError:
            def __str__(self):
                return "bare error"

        batch_err = BatchError(path="root[0]", indices=(0,), error=MinimalError())  # type: ignore
        assert batch_err.code == "ERR"
        assert batch_err.message == "bare error"
        assert str(batch_err) == "root[0]: [ERR] bare error"
