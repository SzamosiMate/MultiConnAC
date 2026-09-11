# Architecture & Style Guide: `multiconn_archicad.utilities`

This document defines the architectural boundaries, design patterns, coding conventions, and testing strategies for the `utilities` subpackage in `multiconn_archicad`.

All contributions to `utilities` must adhere to these guidelines.

---

## 1. Mission & Scope

The `utilities` subpackage provides **Level 3 Ergonomic Sugar** on top of `UnifiedApi`.

### What Belongs in `utilities`:
* **Idiomatic Pythonic wrappers** around repetitive Archicad JSON API interactions (e.g., context managers for resource safety).
* **Batch unwrapping and type coercion** (turning known API response wrappers into Python primitives).
* **Batch result containers** (`BatchResult`, `BatchResult2D`) that preserve explicit one- and two-dimensional alignment while isolating partial failures.
* **Workflow accumulation** (`BatchRun`) that collects failures from multiple steps against the original input items.
* **Universal identifier constructors and normalizers** (e.g., GUID strings / UUIDs $\to$ typed `ElementIdArrayItem` / `PropertyIdArrayItem`).

### What Does NOT Belong in `utilities`:
* **Thin Pass-Through Wrappers:** Functions that merely forward already-constructed CAD models into single API endpoints without normalization, unnesting, or transformation are strictly prohibited.
* **Domain / Business Logic:** Company-specific layer naming, property naming conventions, or pipeline rules belong in downstream applications.
* **In-Memory Caching:** API-bound utilities do not cache CAD state. `BatchRun` is an explicit, short-lived workflow record; it is not a CAD-state cache. Caching policies belong in UI view-models or application pipelines using `functools` or `cachetools`.
* **Heavy Geometric Engines:** Zero `shapely`, CAD polygon clipping, or spatial containment routines.
* **IFC Dependencies:** Zero dependencies on `ifcopenshell`. IFC mappings belong in downstream packages.
* **Transport / Protocol Logic:** Low-level HTTP/socket handling belongs in `core` and `UnifiedApi`.

---

## 2. Core API Design Principles

### A. Bound Operations and Pure Helpers
* API-dependent operations are methods on domain groups such as `PropertyUtilities`, bound to one `UnifiedApi`. They store only the API reference and do not cache BIM data. Payload builders, identifier normalizers, and extractors remain standalone pure functions.
* **Classes:** API-bound utility groups, explicit result/run containers (`BatchResult`, `BatchResult2D`, `BatchRun`), and resource lifecycle context managers (e.g., planned `TeamworkReserve`) are permitted.
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
   * **Return Types:** Returns `BatchResult[T]` for one-dimensional operations and `BatchResult2D[T]` for matrix operations.
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
   * Diagnostic variants return `BatchResult[T]` or `BatchResult2D[T]`, matching the operation shape.
   * Default to standard Python primitives (`str`, `float`, `int`, `bool`, `None`) or standard typed models.

### E. Public Access and Consistent Signatures

Use `header.unified.utilities.property` (or `api.utilities.property` for a standalone
`UnifiedApi`). API operations are implemented directly as methods, with no duplicate
standalone forwarding functions. The former `operation(api, ...)` calling style is
replaced by `api.utilities.property.operation(...)`.

```python
from multiconn_archicad.utilities import Utilities, BatchResult, BatchResult2D, BatchRun
from multiconn_archicad.utilities.properties import create_element_property_values_flat

utils = api.utilities
values = utils.property.get_flat_property_values(elements, property_id)
result = utils.property.set_flat_property_values_result(elements, property_id, values)

# Explicit binding is also available, including for tests:
utils = Utilities(api)

# Pure builders do not need a connection:
payload = create_element_property_values_flat(elements, property_id, values)
```

The package explicitly exports `Utilities`, `BatchResult`, `BatchResult2D`,
`BatchError`, `BatchRun`, and `BatchOperationError`. Import pure helpers directly
from their defining modules.
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
├── results.py            # BatchResult, BatchResult2D, BatchError
├── batch_run.py          # BatchRun and workflow outcome records
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
conversion. Before conversion, payload builders reject direct typed API-error
slots with `BatchOperationError`; other values are opaque and follow the
conversion rules above. The sparse builder deliberately omits typed error
cells and failed rows so that a partial matrix can be written. To intentionally
write an error report, first format the error as a string, such as
`f"[{error.code}] {error.message}"`.

Matrix operations use one outer result slot per element and one inner slot per
property. For two elements and three properties, the result write returns two
rows of three execution results, while the raising setter returns `6` if all
writes succeed. Flat operations use one result slot per element. API response
cardinality is defined by the generated API models; utilities focus on mapping
those responses to the declared result shape.

The following resolution, read, write, and metadata operations are methods on
`api.utilities.property`. Payload builders and `get_possible_enum_values` remain
module-level functions.

* **Resolution:**
  * `resolve_property_ids(...) -> list[PropertyIdArrayItem]` / `resolve_property_ids_result(...) -> BatchResult`
  * `resolve_property_id(...) -> PropertyIdArrayItem` (scalar helper)
* **Reading (2D Engine + 1D/Dict Conveniences):**
  * `get_property_values_per_element(...) -> list[list[str]]` / `..._result(...) -> BatchResult2D`
  * `get_flat_property_values(...) -> list[str]` / `..._result(...) -> BatchResult`
  * `get_property_values_dict_per_element(...) -> list[dict[str, str]]` / `..._result(...) -> BatchResult[dict[str, str]]`
* **Writing (2D Engine + 1D Convenience):**
  * `create_element_property_values` / `create_element_property_values_flat`: Pure dense payload builders converting primitives to CAD mutation models.
  * `create_element_property_values_sparse`: Pure payload builder that derives coordinates from a matrix and omits failed rows/cells.
  * `set_property_values_per_element(...) -> int` / `..._result(...) -> BatchResult2D`
  * `set_flat_property_values(...) -> int` / `..._result(...) -> BatchResult`
* **Inspection:**
  * `get_property_details(...) -> list[PropertyDefinition]` / `..._result(...) -> BatchResult`
  * `get_property_types(...) -> list[str]` / `..._result(...) -> BatchResult`
  * `get_possible_enum_values(property_definition) -> list[str]`: Pure extractor.

---

## 6. Batch Error Handling & Results

`BatchResult[T]` is an immutable one-dimensional result. Each slot holds a successful value or a normalized `BatchError`; `iter_successes()` and `iter_errors()` provide its integer index. `BatchResult2D[T]` is an immutable ragged matrix. It stores the supplied length for each row, including a whole-row error. Matrix errors are located at `(row, column)` or `(row, None)`. Successful values are opaque; only the result's declared slots are interpreted as outcomes.

`map()` transforms only successful slots and lets callback exceptions propagate.
`BatchResult2D.flatten()` returns a flat `BatchResult` in row-major order and
retains cell errors. A whole-row error cannot be flattened and raises a
`ValueError`. `flatten_successes()` and `coordinates()` share one filtering
policy: they omit whole-row and cell errors, and their results are aligned by
position. `BatchResult.successes` is a concrete list for convenient scripting.
Dictionary row failures are represented by one aggregate `BatchError` with
code `-1`; its `causes` retain the original cell or row errors for logging.

```python
result = api.utilities.property.get_flat_property_values_result(elements, property_id)
for element_index, value in result.iter_successes():
    print(element_index, value)
for element_index, error in result.iter_errors():
    print(element_index, error.code, error.message)
```

A partial matrix copy sends only successful cells. The sparse builder derives
the original element/property coordinates directly from the matrix:

```python
run = BatchRun(elements)
read = api.utilities.property.get_property_values_per_element_result(elements, source_properties)
run.record("read", read)
payload = create_element_property_values_sparse(elements, target_properties, read)
write = BatchResult.from_items(api.tapir.property.set_property_values_of_elements(payload))
coordinates = read.coordinates()
run.record(
    "copy",
    write,
    item_indices=[row for row, _ in coordinates],
    details=coordinates,
)
report = run.finish()
```

`BatchRun` accumulates step failures against the original items. `run.report` is an immutable snapshot that contains the item outcomes, recorded steps, overall `BatchStatus`, and optional fatal exception. Before `finish()`, error-free items are incomplete; `finish()` marks them succeeded and closes the run. `abort(exception)` closes the run with overall status `BatchStatus.FAILED`, preserves the fatal exception in `report.fatal_error`, and leaves otherwise clean items incomplete. Start a new `BatchRun` for an explicit retry; completed runs never replace or erase earlier outcomes.

```python
terminal_codes = {4010}  # The application decides which API errors are terminal.
retry_items = []
for outcome in report.outcomes:
    if outcome.succeeded:
        accept(outcome.original_item)
    elif any(failure.error.code in terminal_codes for failure in outcome.failures):
        reject(outcome.original_item, outcome.failures)
    else:
        retry_items.append(outcome.original_item)

retry = BatchRun(retry_items)
# Record fresh retry steps on `retry`; the completed run remains unchanged.
```

The recursive scanner, `root_key`, `items_or`, masks/filtering helpers,
`realign`, `zip`, caught calculation errors, and retry/history replacement were
removed. Dictionary diagnostics use one aggregate error per failed row while
the matrix result retains cell-level detail. A future UI can show consolidated
outcome counts first, then expandable step and coordinate-level failure details.

---

## 7. Testing Strategy

Tests run offline with real official and Tapir Pydantic models and mocked API responses:

```text
tests/utilities/unit/
├── test_identifiers.py
├── test_batch_results.py     # 1D/2D result and BatchRun contracts
└── test_properties.py        # payloads, row aggregation, and partial-copy pipeline
```

The result tests cover direct typed errors, ragged and whole-row matrix failures,
shared flatten filtering, mapping, outcome closure, and atomic recording.
Property tests cover dense and sparse payloads, row-atomic dictionary errors,
and partial writes.

---

## 8. Planned Enhancements / Roadmap

* **Retry support:** Provide UI guidance for starting a separate `BatchRun` from failed original items. No automatic retry loop is provided.

* **`utils.property.get_available_property_ids_of_elements(elements)`**: Query Archicad's `GetAllPropertyNamesOfElements` to check property availability by Classification before executing writes.
* **`elements.py`**: Batch selection getter/setter, element type filtering (e.g., 3D element queries).
* **`attributes.py`**: Layer combinations and visible layer extractors.
* **`teamwork.py`**: Context manager for safe element reservation and automatic sending.

---
