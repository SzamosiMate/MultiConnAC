# Architecture & Style Guide: `multiconn_archicad.utilities`

This document defines the architectural boundaries, design patterns, coding conventions, and testing strategies for the `utilities` subpackage in `multiconn_archicad`.

All contributions to `utilities` must adhere to these guidelines.

---

## 1. Mission & Scope

The `utilities` subpackage provides **Level 3 Ergonomic Sugar** on top of `UnifiedApi`.

### What Belongs in `utilities`:
* **Idiomatic Pythonic wrappers** around repetitive Archicad JSON API interactions (e.g., context managers for resource safety).
* **Batch unwrapping and type coercion** (flattening deeply nested property responses into Python primitives).
* **Batch result containers (`BatchResult`)** that preserve 1:1 index alignment while isolating partial failures and tracking structural error coordinates.
* **Universal identifier constructors and normalizers** (e.g., GUID strings / UUIDs $\to$ typed `ElementIdArrayItem` / `PropertyIdArrayItem`).

### What Does NOT Belong in `utilities`:
* **Thin Pass-Through Wrappers:** Functions that merely forward already-constructed CAD models into single API endpoints without normalization, unnesting, or transformation are strictly prohibited (e.g., do not wrap `set_property_values_of_elements(payload)` if the caller already built the payload—call the client directly).
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
To serve both fast-prototyping computational designers and long-running telemetry pipelines, every bulk operation provides two companion functions:

1. **Standard Function (`<name>`):**
   * **Target:** 90%+ of scripting and pipeline code.
   * **Behavior:** **Fails fast.** If any element or inner property evaluation fails, it immediately raises a descriptive `BatchOperationError`.
   * **Return Types:** Plain Python types (`list[T]`, scalar primitives) for queries, and **`int` (count of mutated items)** for writes.
   * **Implementation:** A clean, 2-line façade over `<name>_result(...)` calling `.raise_for_errors()`.
2. **Diagnostic Variant (`<name>_result`):**
   * **Target:** Telemetry, automated QA checkers, visual loggers, and retry engines.
   * **Behavior:** **Never raises on partial failure.** Isolates failures, preserves 1:1 index alignment, and stores structured `BatchError` entries.
   * **Return Types:** Always returns `BatchResult[T]`.
3. **Scalar Convenience (`<name>` singular):**
   * Provided where intuitive (e.g. `resolve_property_id`), simply delegating to the batch form: `resolve_property_ids(api, [uid])[0]`.

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
def get_property_values_per_element(api: UnifiedApi, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]) -> list[list[Any | None]]:
    ...
```

---

## 3. Code Style & Conciseness Guidelines

We prioritize **concise, high-signal, readable code**:

1. **Horizontal Signatures by Default:**
   Do not split parameters vertically across lines unless there are 5+ parameters. Keep signatures compact and horizontal.
2. **Compose Over Re-inventing Loops:**
   High-level utilities compose over core engines. For instance, 1D flat helpers (`get_flat_property_values`, `set_flat_property_values`) are 1-line wrappers delegating to the 2D matrix engine (`get_property_values_per_element`, `set_property_values_per_element`).
3. **Strict Typing Over Loose Duck-Typing:**
   When an API response returns typed Pydantic models (e.g., `official.PropertyDefinition`), access fields directly (`prop_def.possibleEnumValues`). Do not use defensive `getattr(getattr(...))` chains when the schema is guaranteed.
4. **Concise Idioms, Not Code-Golf:**
   Prefer clean list comprehensions and named helper functions (`accessor=normalize_property_id`) over complex multi-nested comprehensions or multi-line lambdas that construct models.

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
└── attributes.py         # Composite attribute queries (e.g. layer combinations)
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
  * `get_property_values_per_element(...) -> list[list[Any | None]]` / `..._result(...) -> BatchResult`
  * `get_flat_property_values(...) -> list[Any | None]` / `..._result(...) -> BatchResult`
  * `get_property_values_dict_per_element(...) -> list[dict[str, Any | None]]` / `..._result(...) -> BatchResult`
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

In batch CAD operations, round-trips are expensive. When 995 of 1,000 operations succeed and 5 fail, raising a hard exception discards the successes, while silently dropping errors causes off-by-one index alignment bugs. Furthermore, nested errors (such as an unevaluated property on a valid element) must not be silently swallowed into `None`.

### The Contract of `BatchResult[T]`
* **Immutability:** Frozen dataclass value object.
* **Index Alignment:** `len(result.items) == len(input_items)`. Root failures contain `None` in `result.items`; partial successes retain their nested structure (e.g. `["Wall-01", None]`).
* **Multi-Error Mapping:** `result.errors: Mapping[int, tuple[BatchError, ...]]` maps each failed batch index to all errors that occurred on it.
* **Zero Subtree Failures in `successes`:** `result.successes` returns **only** items with zero errors anywhere in their evaluation tree.
* **Truthiness:** `bool(result)` evaluates to `True` **only** if there are zero errors in the entire tree (`is_all_success`).
* **Fail-Fast Trigger:** `result.raise_for_errors(op_name)` raises a consolidated `BatchOperationError` detailing coordinate paths, error codes, and messages, with `err.result` attached.

### Universal Factory: `BatchResult.from_items`
A single factory method handles flat 1D responses, 2D matrices, deeply nested trees, and mutation execution results:
```python
# Queries / Reads:
BatchResult.from_items(raw_response, accessor=..., root_key="elements")

# Mutations / Writes:
BatchResult.from_items(execution_results, root_key="executionResults")
```
It utilizes `find_errors(node, path, indices)` to recursively traverse Pydantic models and lists, producing `BatchError` instances with coordinate paths (e.g. `elements[3].propertyValues[1]`).

### Masking & Filtering Parameters
Instead of forcing input payloads into `BatchResult` at creation time, `BatchResult` provides active instance methods to correlate original input parameters with execution outcomes:

```python
res = set_property_values_per_element_result(api, panels, properties, matrix)

# Padded masks (preserves original input length, replaces failures/successes with fallback):
res.success_mask(panels)              # ["Wall_A", None, "Wall_C"]
res.failure_mask(panels)              # [None, "Wall_B", None]

# Filtered slices (omits items entirely; ideal for retry pipelines):
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
│   ├── test_results.py         # BatchResult contracts, tree errors, masking, raise_for_errors
│   └── test_properties.py      # Contract tests with real Pydantic fixtures & mocks
└── integration/                # Tier 2: Live Archicad tests (Local / Opt-in)
    └── test_properties_live.py # Real socket calls against a running Archicad project
```

1. **Tier 1 (Unit Tests):**
   * Must run completely offline with zero Archicad or network dependencies.
   * Uses real Pydantic models from `official` and `tapir` for mock return data to ensure schema fidelity.
   * Validates both full successes and partial failures (e.g. inner property errors, root element errors, multiple errors on a single item).
2. **Tier 2 (Live Tests):**
   * Marked with `@pytest.mark.live`.
   * Utilizes a session fixture that pings `localhost` Archicad; if unreachable, tests automatically skip (`pytest.skip()`) so CI pipelines remain green.

---

## 8. Planned Enhancements / Roadmap

The following utilities are planned for upcoming releases:
* **`get_available_property_ids_of_elements(api, elements)`**: Query Archicad's `GetAllPropertyNamesOfElements` to check which properties are valid for an element based on its Classification before attempting reads/writes.
* **`elements.py`**: Batch selection getter/setter, element type filtering (e.g., 3D element queries).
* **`attributes.py`**: Layer combinations and visible layer extractors.
* **`teamwork.py`**: Context manager for safe element reservation and automatic sending.
