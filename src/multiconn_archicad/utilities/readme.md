# Architecture & Style Guide: `multiconn_archicad.utilities`

This document defines the architectural boundaries, design patterns, coding conventions, and testing strategies for the `utilities` subpackage in `multiconn_archicad`.

All contributions to `utilities` must adhere to these guidelines.

---

## 1. Mission & Scope

The `utilities` subpackage provides **Level 3 Ergonomic Sugar** on top of `UnifiedApi`.

### What Belongs in `utilities`:
* **Idiomatic Pythonic wrappers** around repetitive Archicad JSON API interactions (e.g., context managers for resource safety).
* **Batch unwrapping and type coercion** (flattening deeply nested property responses into Python primitives).
* **Batch result containers (`BatchResult`)** that preserve 1:1 index alignment while isolating partial failures.
* **Universal identifier constructors and normalizers** (e.g., GUID strings / UUIDs $\to$ typed `ElementIdArrayItem` / `PropertyIdArrayItem`).

### What Does NOT Belong in `utilities`:
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

### B. Batch-First by Default
Archicad JSON API is optimized for bulk operations.
* **Rule:** Never design a utility that takes only a single element if a batch equivalent is possible.
* **Always accept sequences:** Accept `Sequence[ElementIdLike]`, not individual IDs.

### C. Immutability & Liberal Inputs (Postel's Law)
*"Be liberal in what you accept, and conservative in what you send."*

1. **Input Parameters:**
   * Accept liberal union types (`ElementIdLike`, `PropertyIdLike`, `PropertyUserIdLike`) defined in `identifiers.py`.
   * Annotate collection inputs as read-only abstractions: `Sequence[T]` or `Mapping[K, V]` from `collections.abc`.
   * **Never mutate input parameters.** Never pop, append, or modify input collections in-place.
2. **Return Types:**
   * Always return concrete collections (`list[T]`, `dict[K, V]`) or `BatchResult[T]`.
   * Default to **`tapir`** models for identifiers, or unwrap directly to standard Python primitives (`str`, `float`, `int`, `bool`, `None`).

### D. Consistent Signatures
Every utility interacting with Archicad **must take `api: UnifiedApi` as its first parameter**:
```python
def utility_name(api: UnifiedApi, elements: Sequence[ElementIdLike], ...) -> BatchResult[...]:
    ...
```

---

## 3. Code Style & Conciseness Guidelines

We prioritize **concise, high-signal, readable code**:

1. **Horizontal Signatures by Default:**
   Do not split parameters vertically across lines unless there are 5+ parameters. Keep signatures compact and horizontal:
   ```python
   # Recommended
   def get_flat_property_values(api: UnifiedApi, elements: Sequence[ElementIdLike], property_id: PropertyIdLike) -> BatchResult[Any | None]:
       ...
   ```
2. **Compose Over Re-inventing Loops:**
   Do not write manual 30-line `for` loops with duplicate error checks. Compose high-level utilities on top of existing ones (e.g., `get_flat_property_values` and `get_property_values_dict_per_element` both delegate directly to `get_property_values_per_element`).
3. **Strict Typing Over Loose Duck-Typing:**
   When an API response returns typed Pydantic models (e.g. `official.PropertyDefinition`), access fields directly (`prop_def.possibleEnumValues`). Do not use defensive `getattr(getattr(...))` or `hasattr` chains when the schema is guaranteed.
4. **Concise Idioms, Not Code-Golf:**
   Prefer clean list comprehensions and named helper functions (`accessor=normalize_property_id`) over complex multi-nested comprehensions or multi-line lambdas that construct models.

---

## 4. Subpackage Directory Structure

```text
src/multiconn_archicad/utilities/
├── __init__.py           # Clean top-level exports
├── README.md             # This document
├── results.py            # BatchResult and extract_error
├── identifiers.py        # Liberal type aliases & ID normalizers
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
* **Coercion Functions:** `normalize_element_ids()`, `normalize_property_ids()`, `normalize_property_user_id()`, `to_official_property_id_wrapper()`, `split_builtin_name()`.

### `properties.py` (Batch Operations)
* **Reading:**
  * `get_property_values_per_element`: Reads an $N \times M$ matrix, unwrapping to native Python primitives.
  * `get_flat_property_values`: 1D read convenience for a single property across $N$ elements.
  * `get_property_values_dict_per_element`: Reads properties returning `{property_name: value}` dicts.
* **Writing:**
  * `create_element_property_values` / `create_element_property_values_flat`: Pure payload builders.
  * `set_element_property_values`: Low-level batch writer using `BatchResult.from_masked`.
  * `set_flat_property_values`: High-level convenience writer for single properties.
* **Inspection:**
  * `get_property_details`: Fetches full `PropertyDefinition` metadata in bulk.
  * `get_property_types`: Returns type strings (e.g. `"string"`, `"integer"`, `"singleEnum"`).
  * `get_possible_enum_values`: Extracts allowed display strings from an `official.PropertyDefinition`.

---

## 6. Batch Error Handling: `BatchResult[T]`

In batch CAD operations, round-trips are expensive. When 995 of 1,000 operations succeed and 5 fail, raising a hard exception discards the successes, while silently dropping errors causes off-by-one index alignment bugs.

### The Contract of `BatchResult[T]`
* **Immutability:** Frozen dataclass value object.
* **Index Alignment:** `len(result.items) == len(input_elements)`. Failed operations are padded with `None` at their original index.
* **Explicit Errors:** Failures are mapped by input index in `result.errors: Mapping[int, Error]`.
* **Truthiness:** `bool(result)` evaluates to `True` **only** if there are zero errors (`is_all_success`).
* **Strict Assertion:** `result.raise_for_errors()` consolidates all failed indices into a single descriptive `RuntimeError`.

### Factory Methods:
* **`BatchResult.from_items(raw_items, accessor=...)`**: For reads/queries operating on response items.
* **`BatchResult.from_masked(items=payload, mask=executionResults)`**: For writes/mutations mapping input payloads against status response masks.

---

## 7. Testing Strategy

We maintain a strict **2-Tier Testing Strategy**:

```text
tests/utilities/
├── unit/                       # Tier 1: 100% Offline, runs on CI (<1s)
│   ├── test_identifiers.py     # Pure conversions, UUID parsing, type unions
│   └── test_properties.py      # Contract tests with real Pydantic fixtures & mocks
└── integration/                # Tier 2: Live Archicad tests (Local / Opt-in)
    └── test_properties_live.py # Real socket calls against a running Archicad project
```

1. **Tier 1 (Unit Tests):**
   * Must run completely offline with zero Archicad or network dependencies.
   * Uses real Pydantic models from `official` and `tapir` for mock return data to ensure schema fidelity.
   * Validates both full successes and partial failures (e.g. index alignment when `ErrorItem` is returned).
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
```