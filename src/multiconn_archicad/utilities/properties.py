from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from multiconn_archicad import UnifiedApi
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir
from multiconn_archicad.utilities.identifiers import (
    ElementIdLike,
    PropertyIdLike,
    PropertyUserIdLike,
    normalize_element_ids,
    normalize_property_id,
    normalize_property_ids,
    normalize_property_user_id,
    to_official_property_id,
)
from multiconn_archicad.utilities.results import BatchResult

# ==============================================================================
# Internal Unwrappers & Value Coercion
# ==============================================================================


def _unwrap_val(item: Any) -> Any | None:
    pv = getattr(item, "propertyValue", None)
    return getattr(pv, "value", None) if pv is not None else None


def _to_prop_value(val: Any) -> tapir.PropertyValue:
    return val if isinstance(val, tapir.PropertyValue) else tapir.PropertyValue(value="" if val is None else str(val))


def _extract_type_name(item: Any) -> str:
    prop_def = getattr(item, "propertyDefinition", item)
    return str(getattr(prop_def, "type", ""))


# ==============================================================================
# Property ID Resolution
# ==============================================================================


def resolve_property_ids_result(
    api: UnifiedApi, property_user_ids: Sequence[PropertyUserIdLike]
) -> BatchResult[tapir.PropertyIdArrayItem]:
    """Diagnostic batch lookup returning a BatchResult container."""
    raw = api.official.property.get_property_ids([normalize_property_user_id(uid) for uid in property_user_ids])
    items = getattr(raw, "propertyIds", raw)
    return BatchResult.from_items(items, accessor=normalize_property_id, root_key="propertyIds")


def resolve_property_ids(
    api: UnifiedApi, property_user_ids: Sequence[PropertyUserIdLike]
) -> list[tapir.PropertyIdArrayItem]:
    """Fail-fast batch lookup returning a clean list of Tapir PropertyId models."""
    res = resolve_property_ids_result(api, property_user_ids)
    res.raise_for_errors("Property ID resolution")
    return res.successes


def resolve_property_id(
    api: UnifiedApi, property_user_id: PropertyUserIdLike
) -> tapir.PropertyIdArrayItem:
    """Scalar convenience: resolves a single property identifier or raises."""
    return resolve_property_ids(api, [property_user_id])[0]


# ==============================================================================
# Batch Reading & Unwrapping
# ==============================================================================


def get_property_values_per_element_result(
    api: UnifiedApi, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
) -> BatchResult[list[Any | None]]:
    """Diagnostic N x M matrix read returning a BatchResult container."""
    raw = api.tapir.property.get_property_values_of_elements(
        normalize_element_ids(elements), normalize_property_ids(properties)
    )
    items = getattr(raw, "propertyValuesForElements", raw)
    return BatchResult.from_items(
        items,
        accessor=lambda el: [_unwrap_val(p) for p in getattr(el, "propertyValues", [])],
        root_key="elements",
    )


def get_property_values_per_element(
    api: UnifiedApi, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
) -> list[list[Any | None]]:
    """Fail-fast N x M matrix read returning clean Python primitives."""
    res = get_property_values_per_element_result(api, elements, properties)
    res.raise_for_errors("Batch property values read")
    return [row for row in res.items if row is not None]


def get_flat_property_values_result(
    api: UnifiedApi, elements: Sequence[ElementIdLike], property_id: PropertyIdLike
) -> BatchResult[Any | None]:
    """Diagnostic 1D read returning a BatchResult container."""
    res = get_property_values_per_element_result(api, elements, [property_id])
    return BatchResult(
        items=[(row[0] if row is not None else None) for row in res.items],
        errors=res.errors,
    )


def get_flat_property_values(
    api: UnifiedApi, elements: Sequence[ElementIdLike], property_id: PropertyIdLike
) -> list[Any | None]:
    """Fail-fast 1D read returning a flat list of Python primitives."""
    res = get_flat_property_values_result(api, elements, property_id)
    res.raise_for_errors("Single property read")
    return list(res.items)


def get_property_values_dict_per_element_result(
    api: UnifiedApi,
    elements: Sequence[ElementIdLike],
    properties: Sequence[PropertyIdLike],
    property_names: Optional[Sequence[str]] = None,
) -> BatchResult[dict[str, Any | None]]:
    """Diagnostic dictionary read returning a BatchResult container."""
    keys = (
        list(property_names) if property_names else [str(normalize_property_id(p).propertyId.guid) for p in properties]
    )
    res = get_property_values_per_element_result(api, elements, properties)
    return BatchResult(
        items=[(dict(zip(keys, row)) if row is not None else None) for row in res.items],
        errors=res.errors,
    )


def get_property_values_dict_per_element(
    api: UnifiedApi,
    elements: Sequence[ElementIdLike],
    properties: Sequence[PropertyIdLike],
    property_names: Optional[Sequence[str]] = None,
) -> list[dict[str, Any | None]]:
    """Fail-fast dictionary read returning a list of property dictionaries."""
    res = get_property_values_dict_per_element_result(api, elements, properties, property_names)
    res.raise_for_errors("Property dictionary read")
    return [row for row in res.items if row is not None]


# ==============================================================================
# Batch Writing & Payload Builders
# ==============================================================================


def create_element_property_values(
    elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike], values_matrix: Sequence[Sequence[Any]]
) -> list[tapir.ElementPropertyValue]:
    """Builds an N x M list of ElementPropertyValue mutation models."""
    norm_elements = normalize_element_ids(elements)
    norm_props = normalize_property_ids(properties)

    payload: list[tapir.ElementPropertyValue] = []
    for elem, row in zip(norm_elements, values_matrix):
        for prop, val in zip(norm_props, row):
            payload.append(
                tapir.ElementPropertyValue(
                    elementId=elem.elementId,
                    propertyId=prop.propertyId,
                    propertyValue=_to_prop_value(val),
                )
            )
    return payload


def create_element_property_values_flat(
    elements: Sequence[ElementIdLike], property_id: PropertyIdLike, values: Sequence[Any]
) -> list[tapir.ElementPropertyValue]:
    """Builds a 1D list of ElementPropertyValue models mapping elements and values to a single property."""
    pid = normalize_property_id(property_id).propertyId
    return [
        tapir.ElementPropertyValue(elementId=e.elementId, propertyId=pid, propertyValue=_to_prop_value(v))
        for e, v in zip(normalize_element_ids(elements), values)
    ]


def set_property_values_per_element_result(
    api: UnifiedApi,
    elements: Sequence[ElementIdLike],
    properties: Sequence[PropertyIdLike],
    values_matrix: Sequence[Sequence[Any]],
) -> BatchResult[tapir.SuccessfulExecutionResult]:
    """Diagnostic 2D bulk write returning a BatchResult of Archicad execution results."""
    payload = create_element_property_values(elements, properties, values_matrix)
    raw_res = api.tapir.property.set_property_values_of_elements(payload)
    results = getattr(raw_res, "executionResults", raw_res)
    return BatchResult.from_items(results, root_key="executionResults")


def set_property_values_per_element(
    api: UnifiedApi,
    elements: Sequence[ElementIdLike],
    properties: Sequence[PropertyIdLike],
    values_matrix: Sequence[Sequence[Any]],
) -> int:
    """Fail-fast 2D bulk write setting an N x M matrix of property values.

    Returns the count of successfully written property values.
    """
    res = set_property_values_per_element_result(api, elements, properties, values_matrix)
    res.raise_for_errors("Batch property values write")
    return len(res.successes)


def set_flat_property_values_result(
    api: UnifiedApi,
    elements: Sequence[ElementIdLike],
    property_id: PropertyIdLike,
    values: Sequence[Any],
) -> BatchResult[tapir.SuccessfulExecutionResult]:
    """Diagnostic 1D bulk write setting a single property across multiple elements."""
    return set_property_values_per_element_result(api, elements, [property_id], [[v] for v in values])


def set_flat_property_values(
    api: UnifiedApi,
    elements: Sequence[ElementIdLike],
    property_id: PropertyIdLike,
    values: Sequence[Any],
) -> int:
    """Fail-fast 1D bulk write setting a single property across multiple elements.

    Returns the count of successfully written property values.
    """
    res = set_flat_property_values_result(api, elements, property_id, values)
    res.raise_for_errors("Single property write")
    return len(res.successes)


# ==============================================================================
# Metadata & Inspection
# ==============================================================================


def get_property_details_result(
    api: UnifiedApi, properties: Sequence[PropertyIdLike]
) -> BatchResult[official.PropertyDefinition]:
    """Diagnostic metadata lookup returning a BatchResult container."""
    raw = api.official.property.get_details_of_properties([to_official_property_id(p) for p in properties])
    items = getattr(raw, "propertyDefinitions", raw)
    return BatchResult.from_items(
        items, accessor=lambda it: getattr(it, "propertyDefinition", it), root_key="propertyDefinitions"
    )


def get_property_details(
    api: UnifiedApi, properties: Sequence[PropertyIdLike]
) -> list[official.PropertyDefinition]:
    """Fail-fast metadata lookup returning a clean list of PropertyDefinition models."""
    res = get_property_details_result(api, properties)
    res.raise_for_errors("Property details inspection")
    return res.successes


def get_property_types_result(
    api: UnifiedApi, properties: Sequence[PropertyIdLike]
) -> BatchResult[str]:
    """Diagnostic data type names lookup returning a BatchResult container."""
    raw = api.official.property.get_details_of_properties([to_official_property_id(p) for p in properties])
    items = getattr(raw, "propertyDefinitions", raw)
    return BatchResult.from_items(items, accessor=_extract_type_name, root_key="propertyDefinitions")


def get_property_types(
    api: UnifiedApi, properties: Sequence[PropertyIdLike]
) -> list[str]:
    """Fail-fast data type names lookup returning a clean list of type name strings."""
    res = get_property_types_result(api, properties)
    res.raise_for_errors("Property types inspection")
    return res.successes


def get_possible_enum_values(property_definition: official.PropertyDefinition) -> list[str]:
    """Extracts allowed enum display strings from an Official PropertyDefinition."""
    if not property_definition.possibleEnumValues:
        return []
    return [item.enumValue.displayValue for item in property_definition.possibleEnumValues]