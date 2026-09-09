from __future__ import annotations
import pytest
from multiconn_archicad.utilities.results import BatchError, BatchResult
from multiconn_archicad.models.tapir import types as tapir


class TestBatchResultRealign:
    """Sub-batch placement, coordinate translation, and error history."""

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

    def test_realign_unsorted_targets_preserves_nested_coordinates_and_inputs(self):
        error = tapir.ErrorItem(error=tapir.Error(code=42, message="API failure"))
        parent = BatchResult.from_items([0, 1, 2, 3])
        sub = BatchResult.from_items([["ok", error], "success"])
        result = parent.realign(sub, indices=[3, 1], step_name="write")
        assert result.items == [0, "success", 2, ["ok", error]]
        assert result.errors[3][0].path == "write[3][1]"
        assert result.errors[3][0].indices == (3, 1)
        assert sub.errors[0][0].path == "root[0][1]"
        assert parent.errors == {}

    def test_realign_successful_retry_retains_history(self):
        error = tapir.ErrorItem(error=tapir.Error(code=42, message="API failure"))
        parent = BatchResult.from_items([error])
        result = parent.realign(BatchResult.from_items(["fixed"]), indices=[0])
        assert result.items == ["fixed"]
        assert result.errors == parent.errors
        assert result.success_indices == ()
