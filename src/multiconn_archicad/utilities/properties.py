from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from multiconn_archicad import UnifiedApi
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
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir

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


def resolve_property_ids(
    api: UnifiedApi, property_user_ids: Sequence[PropertyUserIdLike]
) -> BatchResult[tapir.PropertyIdArrayItem]:
    """Resolves User-Defined or Built-In property identifiers to Tapir PropertyIdArrayItem models."""
    raw = api.official.property.get_property_ids([normalize_property_user_id(uid) for uid in property_user_ids])
    items = getattr(raw, "propertyIds", raw)
    return BatchResult.from_items(items, accessor=normalize_property_id)


# ==============================================================================
# Batch Reading & Unwrapping
# ==============================================================================


def get_property_values_per_element(
    api: UnifiedApi, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
) -> BatchResult[list[Any | None]]:
    """Reads an N x M matrix of property values across elements, unwrapped to Python primitives."""
    raw = api.tapir.property.get_property_values_of_elements(
        normalize_element_ids(elements), normalize_property_ids(properties)
    )
    items = getattr(raw, "propertyValuesForElements", raw)
    return BatchResult.from_items(
        items, accessor=lambda el: [_unwrap_val(p) for p in getattr(el, "propertyValues", [])]
    )


def get_flat_property_values(
    api: UnifiedApi, elements: Sequence[ElementIdLike], property_id: PropertyIdLike
) -> BatchResult[Any | None]:
    """Reads a single property across elements, unwrapped to a 1D sequence of primitives."""
    res = get_property_values_per_element(api, elements, [property_id])
    return BatchResult(items=[(row[0] if row else None) for row in res.items], errors=res.errors)


def get_property_values_dict_per_element(
    api: UnifiedApi,
    elements: Sequence[ElementIdLike],
    properties: Sequence[PropertyIdLike],
    property_names: Optional[Sequence[str]] = None,
) -> BatchResult[dict[str, Any | None]]:
    """Reads properties in bulk, returning each element's row as a {property_name: value} dictionary."""
    keys = (
        list(property_names) if property_names else [str(normalize_property_id(p).propertyId.guid) for p in properties]
    )
    res = get_property_values_per_element(api, elements, properties)
    return BatchResult(
        items=[(dict(zip(keys, row)) if row is not None else None) for row in res.items], errors=res.errors
    )


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


def set_element_property_values(
    api: UnifiedApi, property_values: Sequence[tapir.ElementPropertyValue]
) -> BatchResult[tapir.ElementPropertyValue]:
    """Direct bulk executor writing ElementPropertyValue items to Archicad."""
    payload = list(property_values)
    res = api.tapir.property.set_property_values_of_elements(payload)
    return BatchResult.from_masked(items=payload, mask=getattr(res, "executionResults", res))


def set_flat_property_values(
    api: UnifiedApi, elements: Sequence[ElementIdLike], property_id: PropertyIdLike, values: Sequence[Any]
) -> BatchResult[tapir.ElementPropertyValue]:
    """High-level bulk write setting a single property across multiple elements."""
    return set_element_property_values(api, create_element_property_values_flat(elements, property_id, values))


# ==============================================================================
# Metadata & Inspection
# ==============================================================================


def get_property_details(
    api: UnifiedApi, properties: Sequence[PropertyIdLike]
) -> BatchResult[official.PropertyDefinition]:
    """Retrieves PropertyDefinition metadata (type, description, possibleEnumValues) in bulk."""
    raw = api.official.property.get_details_of_properties([to_official_property_id(p) for p in properties])
    return BatchResult.from_items(
        getattr(raw, "propertyDefinitions", raw), accessor=lambda it: getattr(it, "propertyDefinition", it)
    )


def get_property_types(api: UnifiedApi, properties: Sequence[PropertyIdLike]) -> BatchResult[str]:
    """Retrieves data type names (e.g. 'string', 'integer', 'boolean') in bulk."""
    raw = api.official.property.get_details_of_properties([to_official_property_id(p) for p in properties])
    return BatchResult.from_items(getattr(raw, "propertyDefinitions", raw), accessor=_extract_type_name)


def get_possible_enum_values(property_definition: official.PropertyDefinition) -> list[str]:
    """Extracts allowed enum display strings from an Official PropertyDefinition."""
    if not property_definition.possibleEnumValues:
        return []
    return [item.enumValue.displayValue for item in property_definition.possibleEnumValues]
