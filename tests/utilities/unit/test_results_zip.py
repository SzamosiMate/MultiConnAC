from __future__ import annotations
import pytest
from multiconn_archicad.utilities.results import BatchError, BatchResult
from multiconn_archicad.models.tapir import types as tapir


class TestBatchResultZip:
    """Branch pairing, shared error deduplication, and downstream composition."""

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
        ancestor_err = BatchError(path="readStep[1]", indices=(1,), error=tapir.Error(code=404, message="Not found"))
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
        ancestor_err = BatchError(path="readStep[1]", indices=(1,), error=tapir.Error(code=404, message="Not found"))
        err_a = BatchError(path="branchA[1]", indices=(1,), error=tapir.Error(code=10, message="Fail A"))
        err_b = BatchError(path="branchB[1]", indices=(1,), error=tapir.Error(code=20, message="Fail B"))

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
        ancestor_err = BatchError(path="read[1]", indices=(1,), error=tapir.Error(code=404, message="Not found"))
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

    def test_zip_then_map_selects_clean_branch(self):
        error = tapir.ErrorItem(error=tapir.Error(code=42, message="API failure"))
        joined = BatchResult.from_items([error]).zip(BatchResult.from_items(["ok"]))
        mapped = joined.map(lambda pair: pair[1])
        assert mapped.items == ["ok"]
        assert mapped.errors == {}

    def test_zip_retains_same_content_at_different_source_paths(self):
        error = tapir.ErrorItem(error=tapir.Error(code=42, message="API failure"))
        left = BatchResult.from_items([error], root_key="left")
        right = BatchResult.from_items([error], root_key="right")
        joined = left.zip(right)
        assert [err.path for err in joined.errors[0]] == ["left[0]", "right[0]"]
        assert left.total_errors == right.total_errors == 1
