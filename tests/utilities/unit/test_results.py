from __future__ import annotations

import pytest
from multiconn_archicad.utilities.results import BatchError, BatchOperationError, BatchResult, extract_error
from multiconn_archicad.models.official import types as official_types
from multiconn_archicad.models.tapir import types as tapir_types


class TestExtractError:
    def test_extracts_from_tapir_failed_execution_result(self):
        err = tapir_types.Error(code=404, message="Element not found")
        item = tapir_types.FailedExecutionResult(error=err)
        assert extract_error(item) == err

    def test_extracts_from_tapir_error_item(self):
        err = tapir_types.Error(code=500, message="Internal error")
        item = tapir_types.ErrorItem(error=err)
        assert extract_error(item) == err

    def test_extracts_from_official_failed_execution_result(self):
        err = official_types.Error(code=400, message="Official execution failure")
        item = official_types.FailedExecutionResult(error=err)
        assert extract_error(item) == err

    def test_extracts_direct_error_model(self):
        err = tapir_types.Error(code=404, message="Element not found")
        assert extract_error(err) == err

    def test_returns_none_for_successful_models(self):
        assert extract_error(tapir_types.SuccessfulExecutionResult()) is None
        assert extract_error(official_types.SuccessfulExecutionResult()) is None


class TestBatchResultFromItems:
    def test_all_successful_flat(self):
        raw = ["elem_1", "elem_2"]
        result = BatchResult.from_items(raw)

        assert result.is_all_success is True
        assert result.items == ["elem_1", "elem_2"]
        assert result.successes == ["elem_1", "elem_2"]
        assert result.errors == {}
        assert result.total_errors == 0

    def test_partial_failure_with_accessor(self):
        err = tapir_types.Error(code=99, message="Unavailable")
        raw = [
            tapir_types.PropertyValue(value="A"),
            tapir_types.ErrorItem(error=err),
            tapir_types.PropertyValue(value="B"),
        ]
        result = BatchResult.from_items(raw, accessor=lambda pv: pv.value)

        assert result.is_all_success is False
        assert result.items == ["A", None, "B"]
        assert result.successes == ["A", "B"]
        assert len(result.errors[1]) == 1
        assert result.errors[1][0].code == 99
        assert result.errors[1][0].path == "root[1]"

    def test_nested_tree_multiple_errors_on_same_item(self):
        """Ensures that multiple errors on the same batch element are completely cached."""
        err1 = tapir_types.Error(code=2, message="Not applicable to classification")
        err2 = tapir_types.Error(code=500, message="Expression division by zero")

        raw = [
            # Element 0 has 1 successful property and 2 failed properties!
            tapir_types.PropertyValuesArrayItem(propertyValues=[
                tapir_types.PropertyValueArrayItem(propertyValue=tapir_types.PropertyValue(value="Wall-01")),
                tapir_types.ErrorItem(error=err1),
                tapir_types.ErrorItem(error=err2),
            ]),
            # Element 1 has all properties successful
            tapir_types.PropertyValuesArrayItem(propertyValues=[
                tapir_types.PropertyValueArrayItem(propertyValue=tapir_types.PropertyValue(value="Wall-02")),
                tapir_types.PropertyValueArrayItem(propertyValue=tapir_types.PropertyValue(value="2800")),
                tapir_types.PropertyValueArrayItem(propertyValue=tapir_types.PropertyValue(value="Soundproof")),
            ]),
        ]

        result = BatchResult.from_items(
            raw,
            accessor=lambda el: [getattr(p.propertyValue, "value", None) if hasattr(p, "propertyValue") else None for p in el.propertyValues],
            root_key="elements",
        )

        assert result.is_all_success is False
        assert result.has_errors is True
        assert result.total_errors == 2

        # Verify Element 0 errors are fully preserved
        assert len(result.errors[0]) == 2
        assert result.errors[0][0].code == 2
        assert result.errors[0][0].path == "elements[0].propertyValues[1]"
        assert result.errors[0][1].code == 500
        assert result.errors[0][1].path == "elements[0].propertyValues[2]"

        # Partial row for Element 0 is preserved
        assert result.items[0] == ["Wall-01", None, None]
        assert result.items[1] == ["Wall-02", "2800", "Soundproof"]

        # Clean successes contains only Element 1
        assert result.successes == [["Wall-02", "2800", "Soundproof"]]


class TestBatchResultDisplayAndShape:
    def test_str_and_repr_all_success(self):
        result = BatchResult.from_items([["Wall-01"], ["Wall-02"]])
        assert str(result) == "BatchResult[list]: All 2 succeeded"
        assert repr(result) == "BatchResult[list](total=2, successes=2, errors=0)"

    def test_str_and_repr_with_nested_errors(self):
        """Ensures that nested errors do NOT misleadingly write 'X/X succeeded'."""
        err1 = tapir_types.Error(code=2, message="Fail 1")
        err2 = tapir_types.Error(code=5, message="Fail 2")

        raw = [
            # Element 0 has 2 errors
            tapir_types.PropertyValuesArrayItem(propertyValues=[
                tapir_types.ErrorItem(error=err1),
                tapir_types.ErrorItem(error=err2),
            ]),
            # Element 1 has 1 success
            tapir_types.PropertyValuesArrayItem(propertyValues=[
                tapir_types.PropertyValueArrayItem(propertyValue=tapir_types.PropertyValue(value="OK")),
            ]),
        ]

        result = BatchResult.from_items(
            raw,
            accessor=lambda el: [getattr(p.propertyValue, "value", None) if hasattr(p, "propertyValue") else None for p in el.propertyValues],
            root_key="elements",
        )

        # Must report 1/2 succeeded, 2 errors across 1 item
        assert str(result) == "BatchResult[list]: 1/2 succeeded (2 error(s) across 1 item(s))"
        assert repr(result) == "BatchResult[list](total=2, successes=1, errors=2)"


class TestDebugDump:
    def test_debug_dump_structure_with_nested_errors(self):
        err = tapir_types.Error(code=2, message="Not evaluated")
        raw = [
            tapir_types.PropertyValuesArrayItem(propertyValues=[
                tapir_types.PropertyValueArrayItem(propertyValue=tapir_types.PropertyValue(value="Wall-01")),
                tapir_types.ErrorItem(error=err),
            ]),
        ]

        result = BatchResult.from_items(
            raw,
            accessor=lambda el: [getattr(p.propertyValue, "value", None) if hasattr(p, "propertyValue") else None for p in el.propertyValues],
            root_key="elements",
        )

        dump = result.debug_dump()
        assert dump["items"] == [["Wall-01", None]]
        assert dump["total_errors"] == 1
        assert 0 in dump["errors"]
        assert dump["errors"][0] == [{
            "path": "elements[0].propertyValues[1]",
            "indices": (0, 1),
            "code": 2,
            "message": "Not evaluated",
        }]


class TestMaskingAndFiltering:
    @pytest.fixture
    def sample_batch_result(self):
        err = tapir_types.Error(code=500, message="Locked")
        raw = [
            tapir_types.SuccessfulExecutionResult(),
            tapir_types.FailedExecutionResult(error=err),
            tapir_types.SuccessfulExecutionResult(),
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
        err = tapir_types.Error(code=404, message="Element deleted")
        result = BatchResult.from_items(["ok", tapir_types.ErrorItem(error=err)], root_key="elements")

        with pytest.raises(BatchOperationError) as exc_info:
            result.raise_for_errors("Element query")

        exc = exc_info.value
        assert isinstance(exc, RuntimeError)
        assert exc.result is result
        assert "Element query failed with 1 error(s) across 1 item(s):" in str(exc)
        assert "- elements[1]: [404] Element deleted" in str(exc)