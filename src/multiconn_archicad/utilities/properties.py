from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from multiconn_archicad import UnifiedApi
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir
from multiconn_archicad.utilities.identifiers import (
    ElementIdLike,
    PropertyIdLike,
    PropertyUserId,
    normalize_element_ids,
    normalize_property_id,
    normalize_property_ids,
    to_official_property_id,
)
from multiconn_archicad.utilities.results import BatchResult

# ==============================================================================
# Internal Unwrappers & Value Coercion
# ==============================================================================


def _extract_property_values(element: tapir.PropertyValuesArrayItem) -> list[str | tapir.ErrorItem]:
    """Extracts string property values, preserving inner ErrorItems on failure."""
    return [
        p.propertyValue.value if isinstance(p, tapir.PropertyValueArrayItem) else p
        for p in getattr(element, "propertyValues", [])
    ]


def _get_raw_property_values(
    api: UnifiedApi, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
) -> list[tapir.ErrorItem | tapir.PropertyValuesArrayItem]:
    return api.tapir.property.get_property_values_of_elements(
        normalize_element_ids(elements), normalize_property_ids(properties)
    )


def _to_prop_value(val: Any) -> tapir.PropertyValue:
    return val if isinstance(val, tapir.PropertyValue) else tapir.PropertyValue(value="" if val is None else str(val))


# ==============================================================================
# Property ID Resolution
# ==============================================================================


def resolve_property_ids_result(
    api: UnifiedApi, property_user_ids: Sequence[PropertyUserId]
) -> BatchResult[tapir.PropertyIdArrayItem]:
    """Diagnostic batch lookup returning a BatchResult container."""
    raw = api.official.property.get_property_ids(property_user_ids)
    return BatchResult.from_items(raw, accessor=normalize_property_id, root_key="propertyIds")


def resolve_property_ids(
    api: UnifiedApi, property_user_ids: Sequence[PropertyUserId]
) -> list[tapir.PropertyIdArrayItem]:
    """Fail-fast batch lookup returning a clean list of Tapir PropertyId models."""
    res = resolve_property_ids_result(api, property_user_ids)
    res.raise_for_errors("Property ID resolution")
    return res.successes


def resolve_property_id(
    api: UnifiedApi, property_user_id: PropertyUserId
) -> tapir.PropertyIdArrayItem:
    """Scalar convenience: resolves a single property identifier or raises."""
    return resolve_property_ids(api, [property_user_id])[0]


# ==============================================================================
# Batch Reading & Unwrapping
# ==============================================================================


def get_property_values_per_element_result(
    api: UnifiedApi, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
) -> BatchResult[list[str]]:
    """Diagnostic N x M matrix read returning a BatchResult container."""
    items = _get_raw_property_values(api, elements, properties)
    return BatchResult.from_items(
        items,
        accessor=_extract_property_values,
        root_key="elements",
    )


def get_property_values_per_element(
    api: UnifiedApi, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
) -> list[list[str]]:
    """Fail-fast N x M matrix read returning clean Python primitives."""
    res = get_property_values_per_element_result(api, elements, properties)
    res.raise_for_errors("Batch property values read")
    return res.successes


def get_flat_property_values_result(
    api: UnifiedApi, elements: Sequence[ElementIdLike], property_id: PropertyIdLike
) -> BatchResult[str]:
    """Diagnostic 1D read returning a BatchResult container."""
    property_values = _get_raw_property_values(api, elements, [property_id])
    return BatchResult.from_items(
        property_values,
        accessor=lambda el: _extract_property_values(el)[0],
        root_key="elements",
    )


def get_flat_property_values(
    api: UnifiedApi, elements: Sequence[ElementIdLike], property_id: PropertyIdLike
) -> list[str]:
    """Fail-fast 1D read returning a flat list of Python primitives."""
    res = get_flat_property_values_result(api, elements, property_id)
    res.raise_for_errors("Single property read")
    return res.successes


def get_property_values_dict_per_element_result(
    api: UnifiedApi,
    elements: Sequence[ElementIdLike],
    properties: Sequence[PropertyIdLike],
    property_names: Optional[Sequence[str]] = None,
) -> BatchResult[dict[str, str | tapir.ErrorItem]]:
    """Diagnostic dictionary read returning a BatchResult container."""
    keys = (
        list(property_names) if property_names else [str(normalize_property_id(p).propertyId.guid) for p in properties]
    )
    raw = _get_raw_property_values(api, elements, properties)
    return BatchResult.from_items(
        raw,
        accessor=lambda el: dict(zip(keys, _extract_property_values(el))),
        root_key="elements",
    )


def get_property_values_dict_per_element(
    api: UnifiedApi,
    elements: Sequence[ElementIdLike],
    properties: Sequence[PropertyIdLike],
    property_names: Optional[Sequence[str]] = None,
) -> list[dict[str, str]]:
    """Fail-fast dictionary read returning a list of property dictionaries."""
    res = get_property_values_dict_per_element_result(api, elements, properties, property_names)
    res.raise_for_errors("Property dictionary read")
    return res.successes


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
    return BatchResult.from_items(raw_res, root_key="executionResults")


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
    property_definition = api.official.property.get_details_of_properties([to_official_property_id(p) for p in properties])
    return BatchResult.from_items(property_definition,  root_key="propertyDefinitions")


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
    property_definition = api.official.property.get_details_of_properties([to_official_property_id(p) for p in properties])
    return BatchResult.from_items(
        property_definition, accessor=lambda it: it.type, root_key="propertyDefinitions"
    )


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