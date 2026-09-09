from __future__ import annotations

import pytest
import uuid
from typing import Any, Optional
from pydantic import BaseModel

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
            tapir.PropertyValuesArrayItem(propertyValues=[
                tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-01")),
                err1,
                err2,
            ]),
            tapir.PropertyValuesArrayItem(propertyValues=[
                tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-02")),
            ]),
        ]

        result = BatchResult.from_items(
            raw,
            accessor=lambda el: [getattr(p.propertyValue, "value", None) if hasattr(p, "propertyValue") else p for p in el.propertyValues],
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
            tapir.PropertyValuesArrayItem(propertyValues=[
                tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="OK")),
            ]),
        ]

        result = BatchResult.from_items(
            raw,
            accessor=lambda el: [getattr(p.propertyValue, "value", None) if hasattr(p, "propertyValue") else p for p in el.propertyValues],
            root_key="elements",
        )

        assert str(result) == "BatchResult[list]: 1/2 succeeded (2 error(s) across 1 item(s))"
        assert repr(result) == "BatchResult[list](total=2, successes=1, errors=2)"


class TestDebugDump:
    def test_debug_dump_structure_with_nested_errors(self):
        err = tapir.ErrorItem(error=tapir.Error(code=2, message="Not evaluated"))
        raw = [
            tapir.PropertyValuesArrayItem(propertyValues=[
                tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-01")),
                err,
            ]),
        ]

        result = BatchResult.from_items(
            raw,
            accessor=lambda el: [getattr(p.propertyValue, "value", None) if hasattr(p, "propertyValue") else p for p in el.propertyValues],
            root_key="elements",
        )

        dump = result.debug_dump()
        assert dump["items"] == [["Wall-01", err]]
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


class ElementModel(BaseModel):
    id: str = "W-1"
    prop: Any = None
    width: Optional[int] = None
    h: Optional[int] = None
    vol: Optional[int] = None


class MultiPropModel(BaseModel):
    p1: Any = None
    p2: Any = None


class NestedErrorModel(BaseModel):
    err: Optional[tapir.ErrorItem] = None


class TestBatchResultMapComprehensive:
    """Comprehensive test matrix implementation for BatchResult.map (M-01 to M-15)."""

    def test_m01_basic_clean(self):
        """M-01: Standard functional functor mapping across clean primitives."""
        result = BatchResult.from_items(["apple", "banana"])
        mapped = result.map(lambda s: s.upper())

        assert mapped.is_all_success is True
        assert mapped.items == ["APPLE", "BANANA"]
        assert mapped.success_indices == (0, 1)
        assert mapped.errors == {}

    def test_m02_empty_batch(self):
        """M-02: Zero items must not raise IndexError or ZeroDivisionError."""
        result = BatchResult.from_items([])
        mapped = result.map(lambda x: x * 2)

        assert mapped.is_all_success is True
        assert mapped.items == []
        assert "total=0" in repr(mapped)

    def test_m03_immutability(self):
        """M-03: Pure value-object contract: operations return a new instance."""
        orig = BatchResult.from_items(["item1", "item2"])
        mapped = orig.map(lambda s: s.upper())

        assert orig.items == ["item1", "item2"]
        assert mapped.items == ["ITEM1", "ITEM2"]
        assert mapped is not orig

    def test_m04_root_error_passthrough(self):
        """M-04: fn is never invoked on root ErrorContainers; error container passes through."""
        err_item = tapir.ErrorItem(error=tapir.Error(code=404, message="Not found"))
        result = BatchResult.from_items(["apple", err_item, "cherry"])

        # fn would raise AttributeError if called on err_item
        mapped = result.map(lambda s: s.upper())

        assert mapped.is_all_success is False
        assert mapped.items == ["APPLE", err_item, "CHERRY"]
        assert mapped.success_indices == (0, 2)
        assert mapped.errors[1][0].code == 404

    def test_m05_composite_healthy_branch(self):
        """M-05: Zombie error clearing when mapping to a clean sub-branch."""
        err_item = tapir.ErrorItem(error=tapir.Error(code=2, message="Bad prop"))
        el = ElementModel(id="W-1", prop=err_item)
        result = BatchResult.from_items([el])

        assert result.is_all_success is False

        mapped = result.map(lambda e: e.id)

        assert mapped.is_all_success is True
        assert mapped.items == ["W-1"]
        assert mapped.successes == ["W-1"]
        assert mapped.errors == {}

    def test_m06_composite_broken_branch(self):
        """M-06: Safe promotion of underlying ErrorItem when fn touches a broken sub-branch."""
        err_item = tapir.ErrorItem(error=tapir.Error(code=2, message="Bad prop"))
        el = ElementModel(id="W-1", prop=err_item)
        result = BatchResult.from_items([el])

        mapped = result.map(lambda e: e.prop.value)

        assert mapped.is_all_success is False
        assert mapped.items == [err_item]  # ErrorItem promoted, no ElementModel left behind!
        assert mapped.items_or(None) == [None]
        assert mapped.errors[0][0].code == 2

    def test_m07_composite_multi_error(self):
        """M-07: Specific error resolution when touching one of multiple broken branches."""
        err1 = tapir.ErrorItem(error=tapir.Error(code=10, message="Err 1"))
        err2 = tapir.ErrorItem(error=tapir.Error(code=20, message="Err 2"))
        el = MultiPropModel(p1=err1, p2=err2)
        result = BatchResult.from_items([el])

        assert len(result.errors[0]) == 2

        mapped = result.map(lambda e: e.p2.value)

        assert mapped.is_all_success is False
        assert mapped.items == [err2]
        # Only p2's error remains; p1's error was cleared as an unselected branch
        assert len(mapped.errors[0]) == 1
        assert mapped.errors[0][0].code == 20
        assert "p2" in mapped.errors[0][0].path

    def test_m08_2d_row_extraction_success(self):
        """M-08: Structural uncurrying from 2D matrix to 1D flat sequence on clean data."""
        matrix = [["Wall-01", "2800"], ["Wall-02", "3000"]]
        result = BatchResult.from_items(matrix)

        mapped = result.map(lambda row: row[0])

        assert mapped.is_all_success is True
        assert mapped.items == ["Wall-01", "Wall-02"]
        assert mapped.errors == {}

    def test_m09_2d_row_extraction_partial(self):
        """M-09: Extracting clean column clears zombie errors from adjacent failed columns."""
        err_item = tapir.ErrorItem(error=tapir.Error(code=500, message="Failed"))
        matrix = [["Wall-01", "2800"], ["Wall-02", err_item]]
        result = BatchResult.from_items(matrix)

        assert result.is_all_success is False

        mapped = result.map(lambda row: row[0])

        assert mapped.is_all_success is True
        assert mapped.items == ["Wall-01", "Wall-02"]
        assert mapped.errors == {}

    def test_m10_2d_row_extraction_error_col(self):
        """M-10: Extracting error column unwraps ErrorItem and registers it."""
        err_item = tapir.ErrorItem(error=tapir.Error(code=500, message="Failed"))
        matrix = [["Wall-01", "2800"], ["Wall-02", err_item]]
        result = BatchResult.from_items(matrix)

        mapped = result.map(lambda row: row[1])

        assert mapped.is_all_success is False
        assert mapped.items == ["2800", err_item]
        assert mapped.successes == ["2800"]
        assert mapped.errors[1][0].code == 500

    def test_m11_write_payload_flattening(self):
        """M-11: 1-element mutation rows unwrapped to flat items without trapping lists."""
        failed_res = tapir.FailedExecutionResult(
            success=False, error=tapir.Error(code=500, message="Lock timeout")
        )
        matrix = [[tapir.SuccessfulExecutionResult()], [failed_res]]
        result = BatchResult.from_items(matrix)

        mapped = result.map(lambda row: row[0])

        assert mapped.is_all_success is False
        assert isinstance(mapped.items[0], tapir.SuccessfulExecutionResult)
        assert mapped.items[1] == failed_res
        assert mapped.success_indices == (0,)
        assert mapped.errors[1][0].code == 500

    def test_m12_calculation_error_absorption(self):
        """M-12: Runtime math errors absorbed into structured BatchError when enabled."""
        el = ElementModel(h=0, vol=10)
        result = BatchResult.from_items([el])

        mapped = result.map(lambda e: e.vol / e.h, catch_calc_errors=True)

        assert mapped.is_all_success is False
        assert isinstance(mapped.items[0], tapir.ErrorItem)
        assert mapped.items[0].error.code == 500
        assert "ZeroDivisionError" in mapped.items[0].error.message
        assert mapped.errors[0][0].path == "map[0]"

    def test_m13_calculation_error_disabled(self):
        """M-13: Runtime exceptions bubble up directly when catch_calc_errors=False."""
        el = ElementModel(h=0, vol=10)
        result = BatchResult.from_items([el])

        with pytest.raises(ZeroDivisionError):
            result.map(lambda e: e.vol / e.h, catch_calc_errors=False)

    def test_m14_unrelated_developer_typo(self):
        """M-14: Developer typos in fn are not swallowed when catch_calc_errors=False."""
        el = ElementModel(width=100)
        result = BatchResult.from_items([el])

        with pytest.raises(AttributeError, match=r"has no attribute 'widht'"):
            result.map(lambda e: e.widht, catch_calc_errors=False)

    def test_m15_fn_introduces_nested_errors(self):
        """M-15: When fn outputs a composite model containing errors, find_errors discovers them."""
        err_item = tapir.ErrorItem(error=tapir.Error(code=1, message="Inner error"))
        result = BatchResult.from_items(["ID-1", "ID-2"])

        mapped = result.map(
            lambda s: NestedErrorModel(err=err_item if s == "ID-2" else None)
        )

        assert mapped.is_all_success is False
        assert mapped.success_indices == (0,)
        assert mapped.errors[1][0].code == 1
        assert mapped.errors[1][0].path == "map[1].err"


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
        
        
class TestBatchResultRealignComprehensive:
    """Comprehensive test matrix implementation for BatchResult.realign (R-01 to R-14)."""

    def test_r01_all_success_passthrough(self):
        """R-01: Baseline 1:1 replacement when both steps have 100% success."""
        parent = BatchResult.from_items(["P0", "P1", "P2"])
        sub = BatchResult.from_items(["W0", "W1", "W2"])

        realigned = parent.realign(sub)

        assert realigned.is_all_success is True
        assert realigned.items == ["W0", "W1", "W2"]
        assert realigned.success_indices == (0, 1, 2)
        assert realigned.errors == {}

    def test_r02_default_splicing_retain_prior_errors(self):
        """R-02: Bypassed failed slots retain parent items and prior errors untouched."""
        err_read = tapir.ErrorItem(error=tapir.Error(code=404, message="Read fail"))
        parent = BatchResult.from_items(["P0", err_read, "P2", "P3"])
        # Parent success_indices are (0, 2, 3)
        sub = BatchResult.from_items(["W0", "W2", "W3"])

        realigned = parent.realign(sub)

        assert realigned.is_all_success is False
        assert realigned.items == ["W0", err_read, "W2", "W3"]
        assert realigned.success_indices == (0, 2, 3)
        assert 1 in realigned.errors
        assert realigned.errors[1][0].code == 404

    def test_r03_sub_batch_error_coordinate_shift(self):
        """R-03: Sub-batch error index is re-mapped from sub-space to master coordinates."""
        err_read = tapir.ErrorItem(error=tapir.Error(code=404, message="Read fail"))
        err_write = tapir.ErrorItem(error=tapir.Error(code=500, message="Write lock"))

        parent = BatchResult.from_items(["P0", err_read, "P2", "P3"])
        # parent.success_indices are (0, 2, 3)
        # In sub: sub-index 1 (which corresponds to master index 2) fails
        sub = BatchResult.from_items(["W0", err_write, "W3"])

        realigned = parent.realign(sub, step_name="writeArea")

        assert realigned.is_all_success is False
        assert realigned.items == ["W0", err_read, err_write, "W3"]
        assert realigned.success_indices == (0, 3)
        assert 1 in realigned.errors
        assert realigned.errors[1][0].code == 404
        assert 2 in realigned.errors
        assert realigned.errors[2][0].code == 500
        assert realigned.errors[2][0].path == "writeArea[2]"
        assert realigned.errors[2][0].indices == (2,)

    def test_r04_error_path_and_indices_tuple_reindexing(self):
        """R-04: Multi-level coordinate paths and index tuples (sub_idx, child_idx) translate to (master_idx, child_idx)."""
        parent = BatchResult.from_items(["P0", "P1", "P2", "P3", "P4"])

        err_model = tapir.Error(code=500, message="Child field error")
        nested_batch_err = BatchError(path="results[1].val", indices=(1, 0), error=err_model)
        sub = BatchResult(
            items=["W2", "W4_failed"],
            errors={1: (nested_batch_err,)},
        )

        realigned = parent.realign(sub, indices=[2, 4], step_name="writeVal")

        assert 4 in realigned.errors
        assert realigned.errors[4][0].indices == (4, 0)
        assert realigned.errors[4][0].path == "writeVal[4].val"
        assert realigned.errors[4][0].code == 500

    def test_r05_empty_sub_batch_total_parent_failure(self):
        """R-05: Empty sub-batch when all parent operations failed executes cleanly."""
        err1 = tapir.ErrorItem(error=tapir.Error(code=1, message="E1"))
        err2 = tapir.ErrorItem(error=tapir.Error(code=2, message="E2"))
        parent = BatchResult.from_items([err1, err2])
        # parent.success_indices is ()
        sub = BatchResult.from_items([])

        realigned = parent.realign(sub)

        assert realigned.items == parent.items
        assert realigned.errors == parent.errors
        assert realigned.success_indices == ()

    def test_r06_custom_filtered_subset_domain_slicing(self):
        """R-06: Arbitrary index sequence replaces only specified master positions."""
        parent = BatchResult.from_items(["P0", "P1", "P2", "P3", "P4"])
        sub = BatchResult.from_items(["W1", "W3"])

        realigned = parent.realign(sub, indices=[1, 3])

        assert realigned.items == ["P0", "W1", "P2", "W3", "P4"]
        assert realigned.is_all_success is True

    def test_r07_multi_error_accumulation_on_same_slot(self):
        """R-07: Errors accumulate into the tuple on a slot that fails in both parent and sub-batch."""
        e_warn = tapir.Error(code=100, message="Warning")
        e_lock = tapir.Error(code=200, message="Locked")

        parent = BatchResult(
            items=["P0", "P1", "P2"],
            errors={1: (BatchError(path="root[1]", indices=(1,), error=e_warn),)},
        )
        sub_err_item = tapir.ErrorItem(error=e_lock)
        sub = BatchResult.from_items([sub_err_item])

        realigned = parent.realign(sub, indices=[1])

        assert realigned.items[1] == sub_err_item
        assert len(realigned.errors[1]) == 2
        assert [e.code for e in realigned.errors[1]] == [100, 200]
        assert realigned.total_errors == 2

    def test_r08_validation_length_mismatch(self):
        """R-08: Rejects sub-batches whose length does not match default success_indices length."""
        err = tapir.ErrorItem(error=tapir.Error(code=1, message="fail"))
        parent = BatchResult.from_items(["P0", "P1", "P2", "P3", err])  # 4 successes
        sub = BatchResult.from_items(["W0", "W1"])  # Length 2 != 4

        with pytest.raises(ValueError, match=r"Sub-batch length \(2\) does not match target indices length \(4\)"):
            parent.realign(sub)

    def test_r09_validation_custom_indices_length_mismatch(self):
        """R-09: Rejects explicit indices sequences that do not match sub-batch length."""
        parent = BatchResult.from_items(["P0", "P1", "P2", "P3", "P4"])
        sub = BatchResult.from_items(["W0", "W1"])

        with pytest.raises(ValueError, match=r"Sub-batch length \(2\) does not match target indices length \(3\)"):
            parent.realign(sub, indices=[0, 1, 2])

    def test_r10_validation_index_out_of_bounds_upper(self):
        """R-10: Rejects target index >= N."""
        parent = BatchResult.from_items(["P0", "P1", "P2", "P3", "P4"])
        sub = BatchResult.from_items(["W0"])

        with pytest.raises(IndexError, match=r"out of bounds for batch size 5"):
            parent.realign(sub, indices=[5])

    def test_r11_validation_index_out_of_bounds_negative(self):
        """R-11: Rejects negative indices to prevent backward wrapping."""
        parent = BatchResult.from_items(["P0", "P1", "P2", "P3", "P4"])
        sub = BatchResult.from_items(["W0"])

        with pytest.raises(IndexError, match=r"out of bounds for batch size 5"):
            parent.realign(sub, indices=[-1])

    def test_r12_validation_duplicate_target_indices(self):
        """R-12: Prevents race conditions by rejecting duplicate target indices."""
        parent = BatchResult.from_items(["P0", "P1", "P2", "P3", "P4"])
        sub = BatchResult.from_items(["W0", "W1"])

        with pytest.raises(ValueError, match="Target indices must be unique"):
            parent.realign(sub, indices=[1, 1])

    def test_r13_immutability_guarantee(self):
        """R-13: Parent and sub instances remain strictly unmodified."""
        parent = BatchResult.from_items(["P0", "P1", "P2"])
        sub = BatchResult.from_items(["W0", "W1"])

        realigned = parent.realign(sub, indices=[0, 1])

        assert parent.items == ["P0", "P1", "P2"]
        assert sub.items == ["W0", "W1"]
        assert realigned is not parent
        assert realigned is not sub

    def test_r14_downstream_masking_on_realigned_batch(self):
        """R-14: Downstream masks and filters work seamlessly on realigned result."""
        err_read = tapir.ErrorItem(error=tapir.Error(code=404, message="Read fail"))
        parent = BatchResult.from_items(["P0", err_read, "P2", "P3"])

        err_write = tapir.ErrorItem(error=tapir.Error(code=500, message="Write fail"))
        sub = BatchResult.from_items(["W0", err_write, "W3"])

        realigned = parent.realign(sub)
        params = ["Wall_A", "Wall_B", "Wall_C", "Wall_D"]

        assert realigned.success_mask(params) == ["Wall_A", None, None, "Wall_D"]
        assert realigned.failure_mask(params) == [None, "Wall_B", "Wall_C", None]
        assert realigned.filter_successful(params) == ["Wall_A", "Wall_D"]
        assert realigned.filter_failed(params) == ["Wall_B", "Wall_C"]
        
        
class TestBatchResultZipComprehensive:
    """Comprehensive test matrix implementation for BatchResult.zip (Z-01 to Z-13)."""

    def test_z01_all_success_pairing(self):
        """Z-01: Baseline 1:1 tuple pairing when both parallel branches have 100% success."""
        branch_a = BatchResult.from_items([1, 2])
        branch_b = BatchResult.from_items(["A", "B"])

        joined = branch_a.zip(branch_b)

        assert joined.is_all_success is True
        assert joined.items == [(1, "A"), (2, "B")]
        assert joined.success_indices == (0, 1)
        assert joined.errors == {}

    def test_z02_left_only_failure(self):
        """Z-02: A failure in the left branch disqualifies slot 1 from mutual success."""
        err_a = tapir.ErrorItem(error=tapir.Error(code=10, message="Left fail"))
        branch_a = BatchResult.from_items([1, err_a])
        branch_b = BatchResult.from_items(["A", "B"])

        joined = branch_a.zip(branch_b)

        assert joined.is_all_success is False
        assert joined.items == [(1, "A"), (err_a, "B")]
        assert joined.success_indices == (0,)
        assert 1 in joined.errors
        assert joined.errors[1][0].code == 10

    def test_z03_right_only_failure(self):
        """Z-03: A failure in the right branch disqualifies slot 1 from mutual success."""
        err_b = tapir.ErrorItem(error=tapir.Error(code=20, message="Right fail"))
        branch_a = BatchResult.from_items([1, 2])
        branch_b = BatchResult.from_items(["A", err_b])

        joined = branch_a.zip(branch_b)

        assert joined.is_all_success is False
        assert joined.items == [(1, "A"), (2, err_b)]
        assert joined.success_indices == (0,)
        assert 1 in joined.errors
        assert joined.errors[1][0].code == 20

    def test_z04_disjoint_failures_zero_mutual_success(self):
        """Z-04: Strict intersection: disjoint failures yield zero mutual successes."""
        err_a = tapir.ErrorItem(error=tapir.Error(code=10, message="Fail A"))
        err_b = tapir.ErrorItem(error=tapir.Error(code=20, message="Fail B"))

        branch_a = BatchResult.from_items([err_a, 2])
        branch_b = BatchResult.from_items(["A", err_b])

        joined = branch_a.zip(branch_b)

        assert joined.is_all_success is False
        assert joined.items == [(err_a, "A"), (2, err_b)]
        assert joined.success_indices == ()
        assert 0 in joined.errors
        assert 1 in joined.errors

    def test_z05_overlapping_independent_failures(self):
        """Z-05: If both branches fail independently on the same item, both errors are retained."""
        err_a = tapir.ErrorItem(error=tapir.Error(code=10, message="Fail A"))
        err_b = tapir.ErrorItem(error=tapir.Error(code=20, message="Fail B"))

        branch_a = BatchResult.from_items([1, err_a])
        branch_b = BatchResult.from_items(["A", err_b])

        joined = branch_a.zip(branch_b)

        assert joined.is_all_success is False
        assert joined.items == [(1, "A"), (err_a, err_b)]
        assert len(joined.errors[1]) == 2
        assert [e.code for e in joined.errors[1]] == [10, 20]
        assert joined.total_errors == 2

    def test_z06_shared_ancestor_error_deduplication(self):
        """Z-06: A common ancestor error inherited by both branches appears exactly once."""
        ancestor_err = BatchError(
            path="readStep[1]", indices=(1,), error=tapir.Error(code=404, message="Not found")
        )
        err_item = tapir.ErrorItem(error=ancestor_err.error)

        branch_a = BatchResult(items=[1, err_item], errors={1: (ancestor_err,)})
        branch_b = BatchResult(items=["A", err_item], errors={1: (ancestor_err,)})

        joined = branch_a.zip(branch_b)

        assert joined.items == [(1, "A"), (err_item, err_item)]
        assert len(joined.errors[1]) == 1
        assert joined.total_errors == 1
        assert joined.errors[1][0] == ancestor_err

    def test_z07_shared_ancestor_plus_independent_branch_errors(self):
        """Z-07: Deduplicates ancestor error while retaining unique branch errors."""
        ancestor_err = BatchError(
            path="readStep[1]", indices=(1,), error=tapir.Error(code=404, message="Not found")
        )
        err_a = BatchError(
            path="branchA[1]", indices=(1,), error=tapir.Error(code=10, message="Fail A")
        )
        err_b = BatchError(
            path="branchB[1]", indices=(1,), error=tapir.Error(code=20, message="Fail B")
        )

        item_a = tapir.ErrorItem(error=err_a.error)
        item_b = tapir.ErrorItem(error=err_b.error)

        branch_a = BatchResult(items=[1, item_a], errors={1: (ancestor_err, err_a)})
        branch_b = BatchResult(items=["A", item_b], errors={1: (ancestor_err, err_b)})

        joined = branch_a.zip(branch_b)

        assert joined.items == [(1, "A"), (item_a, item_b)]
        assert len(joined.errors[1]) == 3
        assert [e.code for e in joined.errors[1]] == [404, 10, 20]
        assert joined.total_errors == 3

    def test_z08_empty_batches(self):
        """Z-08: Zero-length batches join safely without errors."""
        branch_a = BatchResult.from_items([])
        branch_b = BatchResult.from_items([])

        joined = branch_a.zip(branch_b)

        assert joined.is_all_success is True
        assert joined.items == []
        assert joined.total_errors == 0

    def test_z09_validation_length_mismatch(self):
        """Z-09: Rejects merging batches of differing lengths."""
        branch_a = BatchResult.from_items([1, 2, 3])
        branch_b = BatchResult.from_items(["A", "B"])

        with pytest.raises(ValueError, match=r"Cannot zip BatchResult of length 3 with length 2"):
            branch_a.zip(branch_b)

    def test_z10_downstream_filter_and_masking_on_joint_batch(self):
        """Z-10: Step 4 can invoke .filter_successful() directly on the joint batch."""
        err_a = tapir.ErrorItem(error=tapir.Error(code=10, message="E1"))
        err_b = tapir.ErrorItem(error=tapir.Error(code=20, message="E2"))

        branch_a = BatchResult.from_items(["A0", err_a, "A2", "A3"])  # slot 1 failed
        branch_b = BatchResult.from_items(["B0", "B1", err_b, "B3"])  # slot 2 failed

        joined = branch_a.zip(branch_b)
        elements = ["E0", "E1", "E2", "E3"]

        assert joined.filter_successful(elements) == ["E0", "E3"]
        assert joined.failure_mask(elements) == [None, "E1", "E2", None]

    def test_z11_padded_view_on_joint_batch_items_or(self):
        """Z-11: items_or(None) replaces any slot failing in either branch with fallback."""
        err_a = tapir.ErrorItem(error=tapir.Error(code=10, message="E1"))
        branch_a = BatchResult.from_items([1, err_a])
        branch_b = BatchResult.from_items(["A", "B"])

        joined = branch_a.zip(branch_b)

        assert joined.items_or(None) == [(1, "A"), None]

    def test_z12_immutability_guarantee(self):
        """Z-12: Value object purity: neither branch is mutated by the join operation."""
        branch_a = BatchResult.from_items([1, 2])
        branch_b = BatchResult.from_items(["A", "B"])

        joined = branch_a.zip(branch_b)

        assert branch_a.items == [1, 2]
        assert branch_b.items == ["A", "B"]
        assert joined is not branch_a
        assert joined is not branch_b

    def test_z13_multi_branch_chaining_three_plus_branches(self):
        """Z-13: Chaining 3 parallel DAG forks merges and deduplicates correctly."""
        ancestor_err = BatchError(
            path="read[1]", indices=(1,), error=tapir.Error(code=404, message="Not found")
        )
        err_item = tapir.ErrorItem(error=ancestor_err.error)

        branch_a = BatchResult(items=[1, err_item, 3], errors={1: (ancestor_err,)})
        branch_b = BatchResult(items=["A", err_item, "C"], errors={1: (ancestor_err,)})
        branch_c = BatchResult(items=[True, err_item, False], errors={1: (ancestor_err,)})

        joined = branch_a.zip(branch_b).zip(branch_c)

        assert joined.items == [
            ((1, "A"), True),
            ((err_item, err_item), err_item),
            ((3, "C"), False),
        ]
        assert joined.success_indices == (0, 2)
        # The ancestor error must remain deduplicated to exactly 1 entry despite 2 zip operations
        assert len(joined.errors[1]) == 1
        assert joined.total_errors == 1
        assert joined.errors[1][0] == ancestor_err