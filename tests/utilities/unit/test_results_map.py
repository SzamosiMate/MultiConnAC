from __future__ import annotations
import pytest
from typing import Any, Optional
from pydantic import BaseModel
from multiconn_archicad.utilities.results import BatchResult
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir


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


class TestBatchResultMap:
    """Transformations, API error preservation, and callback exception handling."""

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
        failed_res = tapir.FailedExecutionResult(success=False, error=tapir.Error(code=500, message="Lock timeout"))
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

        mapped = result.map(lambda s: NestedErrorModel(err=err_item if s == "ID-2" else None))

        assert mapped.is_all_success is False
        assert mapped.success_indices == (0,)
        assert mapped.errors[1][0].code == 1
        assert mapped.errors[1][0].path == "map[1].err"

    @pytest.mark.parametrize("exc", [TypeError("bad calculation"), IndexError("bad index"), KeyError("root")])
    @pytest.mark.parametrize("catch", [True, False])
    def test_unrelated_exception_with_existing_error(self, exc, catch):
        error = tapir.ErrorItem(error=tapir.Error(code=42, message="API failure"))
        result = BatchResult.from_items([["ok", error]])

        def fail(row):
            raise exc

        if not catch:
            with pytest.raises(type(exc)) as raised:
                result.map(fail, catch_calc_errors=False)
            assert raised.value is exc
        else:
            mapped = result.map(fail, root_key="calculate")
            assert mapped.errors[0][0].code == 500
            assert type(exc).__name__ in mapped.errors[0][0].message
            assert mapped.errors[0][0].path == "calculate[0]"

    def test_equal_errors_promote_the_selected_object(self):
        first = tapir.ErrorItem(error=tapir.Error(code=42, message="same"))
        second = tapir.ErrorItem(error=tapir.Error(code=42, message="same"))
        result = BatchResult.from_items([[first, second]])
        mapped = result.map(lambda row: row[1].value, catch_calc_errors=False)
        assert mapped.items[0] is second
        assert mapped.errors[0][0].path == "root[0][1]"
        assert mapped.errors[0][0].indices == (0, 1)

    def test_external_error_is_not_attributed_to_input(self):
        stored = tapir.ErrorItem(error=tapir.Error(code=1, message="stored"))
        external = tapir.ErrorItem(error=tapir.Error(code=2, message="external"))
        result = BatchResult.from_items([[stored]])
        with pytest.raises(AttributeError):
            result.map(lambda row: external.value, catch_calc_errors=False)

    @pytest.mark.parametrize("models", [tapir, official])
    @pytest.mark.parametrize("kind", ["Error", "ErrorItem", "FailedExecutionResult"])
    def test_direct_errors_are_bypassed_and_unindexed_errors_are_discovered(self, models, kind):
        error = models.Error(code=42, message="API failure")
        item = error if kind == "Error" else getattr(models, kind)(error=error)

        def must_not_run(item):
            pytest.fail("callback was called on an error")

        mapped = BatchResult(items=[item]).map(must_not_run, root_key="custom")
        assert mapped.items[0] is item
        assert mapped.errors[0][0].error is error
        assert mapped.errors[0][0].path == "custom[0]"

    @pytest.mark.parametrize("models", [tapir, official])
    def test_nested_raw_errors_can_be_promoted(self, models):
        error = models.Error(code=42, message="API failure")
        mapped = BatchResult.from_items([[error]]).map(lambda row: row[0].value, catch_calc_errors=False)
        assert mapped.items[0].error is error
        assert mapped.errors[0][0].indices == (0, 0)

    @pytest.mark.parametrize("value", [None, False, 0, "", [], ()])
    def test_clean_falsy_returns_clear_unselected_errors(self, value):
        error = tapir.ErrorItem(error=tapir.Error(code=42, message="API failure"))
        mapped = BatchResult.from_items([[error]]).map(lambda row: value)
        assert mapped.items == [value]
        assert mapped.errors == {}

    def test_callback_failure_does_not_stop_later_items(self):
        mapped = BatchResult.from_items([2, 0, 4]).map(lambda value: 8 / value)
        assert mapped.items_or(None) == [4, None, 2]
        assert mapped.success_indices == (0, 2)

    def test_keyboard_interrupt_propagates(self):
        def interrupt(item):
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            BatchResult.from_items([1]).map(interrupt)

    def test_dictionary_projection_can_keep_or_drop_nested_errors(self):
        error = tapir.ErrorItem(error=tapir.Error(code=42, message="Unavailable"))
        source = BatchResult.from_items([{"ID": "Door-01", "Rating": error}])

        retained = source.map(lambda row: {"FireRating": row["Rating"]})
        clean = source.map(lambda row: {"ID": row["ID"]})

        assert retained.errors[0][0].path == "map[0]['FireRating']"
        assert retained.errors[0][0].indices == (0,)
        assert retained.errors[0][0].error is error.error
        assert clean.items == [{"ID": "Door-01"}]
        assert clean.is_all_success
        assert source.errors[0][0].path == "root[0]['Rating']"

    def test_failed_attribute_access_in_dictionary_preserves_original_error(self):
        error = official.ErrorItem(error=official.Error(code=42, message="Unavailable"))
        source = BatchResult.from_items([{"Rating": error}])

        result = source.map(lambda row: row["Rating"].value, catch_calc_errors=False)

        assert result.items[0] is error
        assert result.errors[0][0] is source.errors[0][0]
