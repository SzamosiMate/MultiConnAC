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

### A. Bound Operations and Pure Helpers
* API-dependent operations are methods on domain groups such as `PropertyUtilities`, bound to one `UnifiedApi`. They store only the API reference and do not cache BIM data. Payload builders, identifier normalizers, and extractors remain standalone pure functions.
* **Classes:** API-bound utility groups, result containers (`BatchResult`, `BatchError`), and resource lifecycle context managers (e.g., planned `TeamworkReserve`) are permitted.
* **No "Active Record" Objects:** Never wrap an Archicad element in a stateful class with instance methods (e.g., `element.get_property()`). This encourages iterative $N+1$ socket calls, severely degrading CAD performance.

### B. The Dedicated Dual-Method Convention
To serve both fast-prototyping scripts and large-scale, eager batch pipelines (e.g., 100k+ elements), bulk operations provide two companion methods:

1. **Standard Method (`<name>`):**
   * **Target:** Simple scripts and rapid prototypes that require a clean result or an exception.
   * **Behavior:** **Raises on reported failure.** After the batch response arrives, any element or inner property failure raises a descriptive `BatchOperationError`. Writes may already have partially succeeded; these helpers provide no rollback or atomicity.
   * **Return Types:** Plain Python types (`list[T]`, scalar primitives) for queries, and **`int` (count of written property values for property setters)** for writes.
   * **Implementation:** A clean façade over `<name>_result(...)` calling `.raise_for_errors()`.
2. **Diagnostic Variant (`<name>_result`):**
   * **Target:** Telemetry, automated QA checkers, GUI viewers, and multi-step eager batch pipelines.
   * **Behavior:** **Retains reported partial failures.** Preserves 1:1 index alignment and stores structured `BatchError` entries. Invalid inputs, transport failures, and whole-command errors can still raise.
   * **Return Types:** Always returns `BatchResult[T]`.
3. **Scalar Convenience (`<name>` singular):**
   * Provided where intuitive (e.g., `resolve_property_id`), simply delegating to the batch form: `self.resolve_property_ids([uid])[0]`.

### C. Batch-First by Default
Archicad JSON API is optimized for bulk operations.
* **Rule:** Never design a utility that takes only a single element if a batch equivalent is possible.
* **Always accept sequences:** Accept `Sequence[ElementIdLike]`, not individual IDs.

### D. Immutability & Liberal Inputs (Postel's Law)
*"Be liberal in what you accept, and conservative in what you send."*

1. **Input Parameters:**
   * Accept liberal union types (`ElementIdLike`, `PropertyIdLike`, `PropertyUserId`) defined in `identifiers.py`.
   * Annotate collection inputs as read-only abstractions: `Sequence[T]` or `Mapping[K, V]` from `collections.abc`.
   * **Never mutate input parameters.** Never pop, append, or modify input collections in-place.
2. **Return Types:**
   * Fail-fast queries return concrete collections (`list[T]`, `dict[K, V]`).
   * Property mutations return `int` (written property value count) when all succeed.
   * Diagnostic variants return `BatchResult[T]`.
   * Default to standard Python primitives (`str`, `float`, `int`, `bool`, `None`) or standard typed models.

### E. Public Access and Consistent Signatures

Use `header.unified.utilities.property` (or `api.utilities.property` for a standalone
`UnifiedApi`). API operations are implemented directly as methods, with no duplicate
standalone forwarding functions. The former `operation(api, ...)` calling style is
replaced by `api.utilities.property.operation(...)`.

```python
from multiconn_archicad.utilities import Utilities, BatchResult
from multiconn_archicad.utilities.properties import create_element_property_values_flat

utils = api.utilities
values = utils.property.get_flat_property_values(elements, property_id)
result = utils.property.set_flat_property_values_result(elements, property_id, values)

# Explicit binding is also available, including for tests:
utils = Utilities(api)

# Pure builders do not need a connection:
payload = create_element_property_values_flat(elements, property_id, values)
```

The package explicitly exports `Utilities`, `BatchResult`, `BatchError`, and
`BatchOperationError`. Import pure helpers directly from their defining modules.
`PropertyUtilities` can be imported from the `properties` module for direct
construction in tests.

Each `UnifiedApi` owns its utilities. Changing a header's port replaces its API and
associated utilities; previously saved API or utilities references still refer to
the old instance. `UnifiedApi` is generated, so its utilities attachment is also
maintained in the API generator.

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
├── __init__.py           # Small public export surface
├── api.py                # Utilities domain-group container
├── readme.md             # This document
├── results.py            # BatchResult, BatchError, find_errors, BatchOperationError
├── identifiers.py        # Liberal type aliases & universal ID normalizers
├── properties.py         # Batch property reading, writing, and inspection
├── elements.py           # Planned: selection get/set, type filtering
├── teamwork.py           # Planned: TeamworkReserve context manager
└── attributes.py         # Planned: composite attribute queries
```

---

## 5. Subpackage Modules Breakdown

### `identifiers.py` (Universal Normalizers)
Centralizes type coercion across all utilities.
* **Input aliases:** `ElementIdLike` and `PropertyIdLike` accept models, UUIDs, and GUID strings. `PropertyUserId` accepts Official `BuiltInPropertyUserId` / `UserDefinedPropertyUserId` models; name tuples are not supported.
* **Coercion Functions:** `normalize_element_id()`, `normalize_element_ids()`, `normalize_property_id()`, `normalize_property_ids()`, `to_official_property_id()`, `split_builtin_name()`.

### `properties.py` (`PropertyUtilities` and Pure Helpers)

#### Value representation and result shape

Value reads use Tapir **display strings**, including numeric properties. They do not
parse numbers or normalize units. Code performing calculations must explicitly
interpret the returned text. Writes preserve `tapir.PropertyValue` instances,
convert `None` to `""`, and otherwise use `str(value)`; this does not perform unit
conversion. Before conversion, both payload builders scan inputs with
`BatchResult.from_items(..., root_key="values").raise_for_errors(...)`.
Typed API errors, including nested errors, raise `BatchOperationError` with input
coordinates (for example, `values[3][2]`) before any API call. Unsupported types
raise `UnsupportedResultNode`; inputs must follow the `find_errors` type contract.
This input validation also applies to diagnostic `_result` setters. To intentionally
write an error report, first format the error as a string, such as
`f"[{error.code}] {error.message}"`.

Matrix operations use one outer result slot per element and one inner slot per
property. For two elements and three properties, the diagnostic write returns two
rows of three execution results, while the raising setter returns `6` if all
writes succeed. Flat operations use one result slot per element. Utilities trust
the client/API response ordering and shape rather than revalidating every response.

The following resolution, read, write, and metadata operations are methods on
`api.utilities.property`. Payload builders and `get_possible_enum_values` remain
module-level functions.

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
* **Shallow freezing:** `@dataclass(frozen=True)` prevents field reassignment. Contained lists, dictionaries, and models remain mutable and may be shared between branches. Container methods do not mutate their inputs; callers and callbacks must also avoid mutating shared data. Deep immutability and thread safety are not guaranteed.
* **Strict Index Alignment:** `len(result.items) == len(input_items)`. Index $i$ always corresponds to item $i$.
* **Typed Error Preservation in `items`:** Failed slots in `result.items` preserve the **raw Error container model** (`ErrorItem`, `FailedExecutionResult`). Composite items retain nested errors. A successful `map()` projection can discard errors from branches it does not return; this container is not a complete audit log.
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
It utilizes `find_errors(node, path, indices)` to recursively traverse Pydantic models, lists/tuples, and dictionary values, extracting `BatchError` instances with coordinate paths (e.g., `elements[3].propertyValues[1]` or `elements[3]['FireRating']`). Dictionary keys appear in paths, while `indices` contains only list/tuple positions. Only typed API error models are recognized as errors; a plain dictionary containing `code` and `message` is ordinary data.

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
* **Composite items with partial errors:** `fn(item)` is attempted. An `AttributeError` whose target contains a recorded API error promotes that original error container and preserves its original coordinates. Identity of the contained API error links the exception to the recorded failure. Unrelated attribute errors and key/index/type errors follow the calculation-error policy.
* **Computation safety:** Callback exceptions become calculation errors by default; `catch_calc_errors=False` lets them propagate. Supported return values are rescanned, so a clean projection clears unselected errors. Unsupported return types raise `UnsupportedResultNode` regardless of this flag.

#### 2. Splicing Sub-Batches Back to Master Coordinates (`.realign()`)
When writing to Archicad, you must not send failed elements over the socket. You filter the inputs, send the sub-batch ($K \le N$), and use `.realign()` to scatter the results back into the master array.

```python
# Sub-batch write (only sends the 9,800 healthy items)
valid_elements = step2.filter_successful(elements)
sub_res = api.utilities.property.set_flat_property_values_result(valid_elements, prop_area, step2.successes)

# Realign scatters the 9,800 results back into the 10,000-element master track.
# By default, indices=step2.success_indices automatically!
step3 = step2.realign(sub_res, step_name="writeArea")

assert len(step3.items) == 10000  # Index alignment perfectly preserved!
```
* **Preserves history:** All prior errors are retained, including errors at explicitly targeted retry indices. A successful retry currently does not clear an earlier failure or restore that index to `success_indices`.
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
res = api.utilities.property.set_property_values_per_element_result(panels, properties, matrix)

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
│   ├── test_utilities_api.py   # Namespace and independent API bindings
│   ├── test_results.py         # BatchResult contracts, tree errors, masking
│   ├── test_results_map.py     # Projection and calculation errors
│   ├── test_results_realign.py # Sub-batch alignment and history
│   ├── test_results_zip.py     # Branch joining and error merging
│   └── test_properties.py      # Contract tests with real Pydantic fixtures & mocks
└── integration/                # Planned Tier 2: Live Archicad tests (Local / Opt-in)
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

* **Retry support:** Define how a successful explicit retry clears an active failure while retaining useful history. This is lower priority: many Archicad failures need human intervention before retrying. No automatic retry loop is currently provided.

* **`utils.property.get_available_property_ids_of_elements(elements)`**: Query Archicad's `GetAllPropertyNamesOfElements` to check property availability by Classification before executing writes.
* **`elements.py`**: Batch selection getter/setter, element type filtering (e.g., 3D element queries).
* **`attributes.py`**: Layer combinations and visible layer extractors.
* **`teamwork.py`**: Context manager for safe element reservation and automatic sending.
