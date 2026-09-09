# Architecture & Style Guide: `multiconn_archicad.utilities`

This document defines the architectural boundaries, design patterns, coding conventions, and testing strategies for the `utilities` subpackage in `multiconn_archicad`.

All contributions to `utilities` must adhere to these guidelines.

---

## 1. Mission & Scope

The `utilities` subpackage provides **Level 3 Ergonomic Sugar** on top of `UnifiedApi`.

### What Belongs in `utilities`:
* **Idiomatic Pythonic wrappers** around repetitive Archicad JSON API interactions (e.g., context managers for resource safety).
* **Batch unwrapping and type coercion** (flattening deeply nested property responses into Python primitives).
* **Batch result containers (`BatchResult`)** that preserve 1:1 index alignment while isolating partial failures and tracking structural error coordinates across multi-step pipelines.
* **Universal identifier constructors and normalizers** (e.g., GUID strings / UUIDs $\to$ typed `ElementIdArrayItem` / `PropertyIdArrayItem`).

### What Does NOT Belong in `utilities`:
* **Thin Pass-Through Wrappers:** Functions that merely forward already-constructed CAD models into single API endpoints without normalization, unnesting, or transformation are strictly prohibited.
* **Domain / Business Logic:** Company-specific layer naming, property naming conventions, or pipeline rules belong in downstream applications.
* **In-Memory Caching:** `utilities` is strictly **100% stateless**. Caching mutable CAD state leads to cache-invalidation bugs in collaborative (Teamwork) environments; caching policies belong in UI view-models or application pipelines using `functools` or `cachetools`.
* **Heavy Geometric Engines:** Zero `shapely`, CAD polygon clipping, or spatial containment routines.
* **IFC Dependencies:** Zero dependencies on `ifcopenshell`. IFC mappings belong in downstream packages.
* **Transport / Protocol Logic:** Low-level HTTP/socket handling belongs in `core` and `UnifiedApi`.

---

## 2. Core API Design Principles

### A. Pure Functions First (Strict Statelessness)
* Utilities are stateless, standalone pure functions.
* **Classes are permitted only for Resource Lifecycle (Context Managers):** e.g., `TeamworkReserve`.
* **No "Active Record" Objects:** Never wrap an Archicad element in a stateful class with instance methods (e.g., `element.get_property()`). This encourages iterative $N+1$ socket calls, severely degrading CAD performance.

### B. The Dedicated Dual-Method Convention
To serve both fast-prototyping scripts and large-scale, eager batch pipelines (e.g., 100k+ elements), bulk operations provide two companion functions:

1. **Standard Function (`<name>`):**
   * **Target:** Simple scripts and rapid prototypes requiring all-or-nothing execution.
   * **Behavior:** **Fails fast.** If any element or inner property evaluation fails, it immediately raises a descriptive `BatchOperationError`.
   * **Return Types:** Plain Python types (`list[T]`, scalar primitives) for queries, and **`int` (count of mutated items)** for writes.
   * **Implementation:** A clean façade over `<name>_result(...)` calling `.raise_for_errors()`.
2. **Diagnostic Variant (`<name>_result`):**
   * **Target:** Telemetry, automated QA checkers, GUI viewers, and multi-step eager batch pipelines.
   * **Behavior:** **Never raises on partial failure.** Isolates failures, preserves 1:1 index alignment, and stores structured `BatchError` entries.
   * **Return Types:** Always returns `BatchResult[T]`.
3. **Scalar Convenience (`<name>` singular):**
   * Provided where intuitive (e.g., `resolve_property_id`), simply delegating to the batch form: `resolve_property_ids(api, [uid])[0]`.

### C. Batch-First by Default
Archicad JSON API is optimized for bulk operations.
* **Rule:** Never design a utility that takes only a single element if a batch equivalent is possible.
* **Always accept sequences:** Accept `Sequence[ElementIdLike]`, not individual IDs.

### D. Immutability & Liberal Inputs (Postel's Law)
*"Be liberal in what you accept, and conservative in what you send."*

1. **Input Parameters:**
   * Accept liberal union types (`ElementIdLike`, `PropertyIdLike`, `PropertyUserIdLike`) defined in `identifiers.py`.
   * Annotate collection inputs as read-only abstractions: `Sequence[T]` or `Mapping[K, V]` from `collections.abc`.
   * **Never mutate input parameters.** Never pop, append, or modify input collections in-place.
2. **Return Types:**
   * Fail-fast queries return concrete collections (`list[T]`, `dict[K, V]`).
   * Fail-fast mutations return `int` (affected items count).
   * Diagnostic variants return `BatchResult[T]`.
   * Default to standard Python primitives (`str`, `float`, `int`, `bool`, `None`) or standard typed models.

### E. Consistent Signatures
Every utility interacting with Archicad **must take `api: UnifiedApi` as its first parameter**:
```python
def get_property_values_per_element(api: UnifiedApi, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]) -> list[list[Any]]:
    ...
```

---

## 3. Code Style & Conciseness Guidelines

1. **Horizontal Signatures by Default:**
   Do not split parameters vertically across lines unless there are 5+ parameters. Keep signatures compact and horizontal.
2. **Compose Over Re-inventing Loops:**
   High-level utilities compose over core engines. 1D flat helpers (`get_flat_property_values`, `set_flat_property_values`) delegate directly to optimized batch payloads without duplicating parsing logic.
3. **Strict Typing Over Loose Duck-Typing:**
   When an API response returns typed Pydantic models (e.g., `official.PropertyDefinition`), access fields directly (`prop_def.possibleEnumValues`). Do not use defensive `getattr(...)` chains when schemas are guaranteed.
4. **Concise Idioms, Not Code-Golf:**
   Prefer clean list comprehensions and named helper functions (`accessor=normalize_property_id`) over complex multi-nested comprehensions.

---

## 4. Subpackage Directory Structure

```text
src/multiconn_archicad/utilities/
├── __init__.py           # Clean top-level exports (dual methods, builders, BatchResult)
├── README.md             # This document
├── results.py            # BatchResult, BatchError, find_errors, BatchOperationError
├── identifiers.py        # Liberal type aliases & universal ID normalizers
├── properties.py         # Batch property reading, writing, and inspection
├── elements.py           # Selection get/set, type filtering
├── teamwork.py           # TeamworkReserve context manager
└── attributes.py         # Composite attribute queries (e.g., layer combinations)
```

---

## 5. Subpackage Modules Breakdown

### `identifiers.py` (Universal Normalizers)
Centralizes type coercion across all utilities.
* **Liberal Aliases:** `ElementIdLike`, `PropertyIdLike`, `PropertyUserIdLike`.
* **Coercion Functions:** `normalize_element_id()`, `normalize_element_ids()`, `normalize_property_id()`, `normalize_property_ids()`, `normalize_property_user_id()`, `to_official_property_id()`, `split_builtin_name()`.

### `properties.py` (Batch Operations)
* **Resolution:**
  * `resolve_property_ids(...) -> list[PropertyIdArrayItem]` / `resolve_property_ids_result(...) -> BatchResult`
  * `resolve_property_id(...) -> PropertyIdArrayItem` (scalar helper)
* **Reading (2D Engine + 1D/Dict Conveniences):**
  * `get_property_values_per_element(...) -> list[list[str]]` / `..._result(...) -> BatchResult`
  * `get_flat_property_values(...) -> list[str]` / `..._result(...) -> BatchResult`
  * `get_property_values_dict_per_element(...) -> list[dict[str, str]]` / `..._result(...) -> BatchResult`
* **Writing (2D Engine + 1D Convenience):**
  * `create_element_property_values` / `create_element_property_values_flat`: Pure payload builders converting primitives to CAD mutation models.
  * `set_property_values_per_element(...) -> int` / `..._result(...) -> BatchResult`
  * `set_flat_property_values(...) -> int` / `..._result(...) -> BatchResult`
* **Inspection:**
  * `get_property_details(...) -> list[PropertyDefinition]` / `..._result(...) -> BatchResult`
  * `get_property_types(...) -> list[str]` / `..._result(...) -> BatchResult`
  * `get_possible_enum_values(property_definition) -> list[str]`: Pure extractor.

---

## 6. Batch Error Handling & Results: `BatchResult[T]`

In large-scale CAD operations (e.g., updating 100,000 properties), all-or-nothing execution is unacceptable: one element on a locked layer or an unplaced door would abort the entire batch. `BatchResult[T]` provides an eager, resilient container designed for multi-step data pipelines.

### The Contract of `BatchResult[T]`
* **Immutability:** Frozen dataclass value object (`@dataclass(frozen=True)`). Safe for concurrent branching.
* **Strict Index Alignment:** `len(result.items) == len(input_items)`. Index $i$ always corresponds to item $i$.
* **Typed Error Preservation in `items`:** Failed slots in `result.items` preserve the **raw Error container model** (`ErrorItem`, `FailedExecutionResult`). Errors are **never** silently dropped or replaced with `None`.
* **Padded Fallback (`.items_or(fallback)`):** When consuming code requires a padded primitive list (e.g., for GUI tables or export matrices), calling `.items_or(None)` returns a sequence with all failed indices replaced by `fallback`.
* **Multi-Error Mapping:** `result.errors: Mapping[int, tuple[BatchError, ...]]` maps each batch index to all errors that occurred on it.
* **Clean Success Slices:**
  * `result.successes`: Returns only items with zero errors anywhere in their evaluation tree.
  * `result.success_indices`: Returns an immutable tuple of integer indices (`tuple[int, ...]`) of all healthy items.
* **Truthiness:** `bool(result)` evaluates to `True` **only** if every item in the batch succeeded without error (`is_all_success`).
* **Fail-Fast Trigger:** `result.raise_for_errors(op_name)` raises a consolidated `BatchOperationError` detailing coordinate paths, error codes, and messages, with `err.result` attached.

---

### Universal Factory: `BatchResult.from_items`

A single factory handles flat 1D sequences, 2D matrices, composite models, and mutation results:
```python
# Queries / Reads:
BatchResult.from_items(raw_response, accessor=..., root_key="elements")

# Mutations / Writes:
BatchResult.from_items(execution_results, root_key="executionResults")
```
It utilizes `find_errors(node, path, indices)` to recursively traverse Pydantic models and lists, extracting `BatchError` instances with coordinate paths (e.g., `elements[3].propertyValues[1]`).

---

### Multi-Step Waterfall Pipelines (Railway-Oriented Processing)

When building multi-step pipelines (Read $\to$ Transform $\to$ Write $\to$ Report), `BatchResult` prevents **Index Drift** (where filtering out failed items shrinks the array and decouples indices from the original inputs).

```text
Master Coordinates (N=10,000)
    │
    ├─ Step 1: Read (returns BatchResult of 10,000)
    │
    ├─ Step 2: Transform (.map() transforms values, absorbs calculation bugs)
    │
    ├─ Branching (Fork/Join):
    │     ├── Branch 3A: Write Property A ──> .realign() ──> 10,000 slots
    │     └── Branch 3B: Write Property B ──> .realign() ──> 10,000 slots
    │     └── Joined via .zip()           ──> Intersection of successes (10,000 slots)
    │
    ├─ Step 4: Write Final Result ──────────> .realign() ──> 10,000 slots
    │
    └─ Step 5: Unified Error Report (Every step's errors aligned to Master Index i)
```

#### 1. Resilient Transformation (`.map(fn)`)
Transforms healthy items while safely navigating around broken branches:
* **Healthy items:** Evaluated via `fn(item)`.
* **Direct error models:** Passed through untouched without executing `fn`.
* **Composite items with partial errors:** `fn(item)` is attempted. If `fn` navigates into a broken branch (raising `AttributeError`, `KeyError`, `IndexError`), the underlying `ErrorItem` is promoted to that slot rather than crashing the batch.
* **Computation safety:** If `fn(item)` raises calculation errors (e.g., `ZeroDivisionError`, `ValueError`), they are captured into a structured `BatchError` at that coordinate.

#### 2. Splicing Sub-Batches Back to Master Coordinates (`.realign()`)
When writing to Archicad, you must not send failed elements over the socket. You filter the inputs, send the sub-batch ($K \le N$), and use `.realign()` to scatter the results back into the master array.

```python
# Sub-batch write (only sends the 9,800 healthy items)
valid_elements = step2.filter_successful(elements)
sub_res = set_flat_property_values_result(api, valid_elements, prop_area, step2.successes)

# Realign scatters the 9,800 results back into the 10,000-element master track.
# By default, indices=step2.success_indices automatically!
step3 = step2.realign(sub_res, step_name="writeArea")

assert len(step3.items) == 10000  # Index alignment perfectly preserved!
```
* **Preserves history:** Bypassed indices retain their prior errors from Steps 1 and 2.
* **Re-indexes coordinates:** Sub-batch error coordinates are re-mapped to their master index ($0 \dots N-1$).

#### 3. Fork-Join Branch Merging (`.zip()`)
When two parallel branches run (e.g., writing Fire Rating in 3A and Acoustic Rating in 3B), both realign to master length $N$. You then `.zip()` them:
```python
# Joins two parallel branches of length N
step3_joined = step3_a.zip(step3_b)
```
* **Items paired:** `(item_a, item_b)`.
* **Errors unioned:** Merges errors from both branches, deduplicating shared ancestor errors.
* **Successes intersected:** `step3_joined.success_indices` contains **only** elements that succeeded in *both* branches.

---

### Masking & Filtering Parameters

To correlate external data sequences with batch results without altering container shapes:

```python
res = set_property_values_per_element_result(api, panels, properties, matrix)

# Padded masks (preserves original input length, replaces failures/successes with fallback):
res.success_mask(panels)              # ["Wall_A", None, "Wall_C"]
res.failure_mask(panels)              # [None, "Wall_B", None]

# Filtered slices (omits items entirely; ideal for sub-batch inputs):
res.filter_successful(panels)         # ["Wall_A", "Wall_C"]
res.filter_failed(panels)             # ["Wall_B"]
```

---

## 7. Testing Strategy

We maintain a strict **2-Tier Testing Strategy**:

```text
tests/utilities/
├── unit/                       # Tier 1: 100% Offline, runs on CI (<1s)
│   ├── test_identifiers.py     # Pure conversions, UUID parsing, type unions
│   ├── test_results.py         # BatchResult contracts, tree errors, masking, map, realign, zip
│   └── test_properties.py      # Contract tests with real Pydantic fixtures & mocks
└── integration/                # Tier 2: Live Archicad tests (Local / Opt-in)
    └── test_properties_live.py # Real socket calls against a running Archicad project
```

1. **Tier 1 (Unit Tests):**
   * Must run completely offline with zero Archicad or network dependencies.
   * Uses real Pydantic models from `official` and `tapir` for mock return data to ensure schema fidelity.
   * Validates full successes, root failures, inner/nested errors, array splicing (`realign`), and branch merging (`zip`).
2. **Tier 2 (Live Tests):**
   * Marked with `@pytest.mark.live`.
   * Automatically skips (`pytest.skip()`) if local Archicad instance is unreachable so CI pipelines remain green.

---

## 8. Planned Enhancements / Roadmap

* **`get_available_property_ids_of_elements(api, elements)`**: Query Archicad's `GetAllPropertyNamesOfElements` to check property availability by Classification before executing writes.
* **`elements.py`**: Batch selection getter/setter, element type filtering (e.g., 3D element queries).
* **`attributes.py`**: Layer combinations and visible layer extractors.
* **`teamwork.py`**: Context manager for safe element reservation and automatic sending.
