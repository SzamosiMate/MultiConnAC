from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional

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

if TYPE_CHECKING:
    from multiconn_archicad.clients.unified_api.api import UnifiedApi


def _extract_property_values(element: tapir.PropertyValuesArrayItem) -> list[str | tapir.ErrorItem]:
    """Extracts string property values, preserving inner ErrorItems on failure."""
    return [p.propertyValue.value if isinstance(p, tapir.PropertyValueArrayItem) else p for p in element.propertyValues]


def _to_prop_value(val: Any) -> tapir.PropertyValue:
    return val if isinstance(val, tapir.PropertyValue) else tapir.PropertyValue(value="" if val is None else str(val))


def create_element_property_values(
    elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike], values_matrix: Sequence[Sequence[Any]]
) -> list[tapir.ElementPropertyValue]:
    """Build an N x M payload using display strings.

    PropertyValue models pass through; None becomes an empty string and other
    values use str(value). No numeric formatting or unit conversion is performed.
    Inputs must be supported by find_errors. Typed API errors, including nested
    errors, raise BatchOperationError before conversion. Format errors as strings
    explicitly when intentionally writing diagnostic text.
    """
    BatchResult.from_items(values_matrix, root_key="values").raise_for_errors("Property write input")
    norm_elements = normalize_element_ids(elements)
    norm_props = normalize_property_ids(properties)
    if len(norm_elements) != len(values_matrix):
        raise ValueError(f"Expected {len(norm_elements)} rows in values_matrix, got {len(values_matrix)}.")

    payload: list[tapir.ElementPropertyValue] = []
    for elem, row in zip(norm_elements, values_matrix):
        if len(norm_props) != len(row):
            raise ValueError(f"Expected {len(norm_props)} values per row, got {len(row)}.")
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
    """Build a single-property payload using display strings.

    PropertyValue models pass through; None becomes an empty string and other
    values use str(value). No numeric formatting or unit conversion is performed.
    Inputs must be supported by find_errors. Typed API errors, including nested
    errors, raise BatchOperationError before conversion. Format errors as strings
    explicitly when intentionally writing diagnostic text.
    """
    BatchResult.from_items(values, root_key="values").raise_for_errors("Property write input")
    pid = normalize_property_id(property_id).propertyId
    if len(elements) != len(values):
        raise ValueError(f"Expected {len(elements)} rows in values, got {len(values)}.")
    return [
        tapir.ElementPropertyValue(elementId=e.elementId, propertyId=pid, propertyValue=_to_prop_value(v))
        for e, v in zip(normalize_element_ids(elements), values)
    ]


def get_possible_enum_values(property_definition: official.PropertyDefinition) -> list[str]:
    """Extracts allowed enum display strings from an Official PropertyDefinition."""
    if not property_definition.possibleEnumValues:
        return []
    return [item.enumValue.displayValue for item in property_definition.possibleEnumValues]


class PropertyUtilities:
    """Batch property operations bound to one UnifiedApi instance.

    Holds only the API reference; property data is not cached. Reads return Tapir
    display strings. Pure payload builders and extractors remain module functions.
    """

    def __init__(self, api: UnifiedApi):
        self._api = api

    def _get_raw_property_values(
        self, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
    ) -> list[tapir.ErrorItem | tapir.PropertyValuesArrayItem]:
        return self._api.tapir.property.get_property_values_of_elements(
            normalize_element_ids(elements), normalize_property_ids(properties)
        )

    def resolve_property_ids_result(
        self, property_user_ids: Sequence[PropertyUserId]
    ) -> BatchResult[tapir.PropertyIdArrayItem]:
        """Diagnostic batch lookup returning a BatchResult container."""
        raw = self._api.official.property.get_property_ids(property_user_ids)
        return BatchResult.from_items(raw, accessor=normalize_property_id, root_key="propertyIds")

    def resolve_property_ids(self, property_user_ids: Sequence[PropertyUserId]) -> list[tapir.PropertyIdArrayItem]:
        """Fail-fast batch lookup returning a clean list of Tapir PropertyId models."""
        res = self.resolve_property_ids_result(property_user_ids)
        res.raise_for_errors("Property ID resolution")
        return res.successes

    def resolve_property_id(self, property_user_id: PropertyUserId) -> tapir.PropertyIdArrayItem:
        """Scalar convenience: resolves a single property identifier or raises."""
        return self.resolve_property_ids([property_user_id])[0]

    def get_property_values_per_element_result(
        self, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
    ) -> BatchResult[list[str | tapir.ErrorItem]]:
        """Read display strings: one row per element, with nested ErrorItems on failure."""
        items = self._get_raw_property_values(elements, properties)
        return BatchResult.from_items(
            items,
            accessor=_extract_property_values,
            root_key="elements",
        )

    def get_property_values_per_element(
        self, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
    ) -> list[list[str]]:
        """Read an N x M matrix of display strings; raise on any reported failure.

        Values are not parsed as numbers or converted to standard units.
        """
        res = self.get_property_values_per_element_result(elements, properties)
        res.raise_for_errors("Batch property values read")
        return res.successes

    def get_flat_property_values_result(
        self, elements: Sequence[ElementIdLike], property_id: PropertyIdLike
    ) -> BatchResult[str]:
        """Read one property as display strings, retaining per-element failures."""
        property_values = self._get_raw_property_values(elements, [property_id])
        return BatchResult.from_items(
            property_values,
            accessor=lambda el: _extract_property_values(el)[0],
            root_key="elements",
        )

    def get_flat_property_values(self, elements: Sequence[ElementIdLike], property_id: PropertyIdLike) -> list[str]:
        """Read one property as display strings; raise on any reported failure.

        Values are not parsed as numbers or converted to standard units.
        """
        res = self.get_flat_property_values_result(elements, property_id)
        res.raise_for_errors("Single property read")
        return res.successes

    def get_property_values_dict_per_element_result(
        self,
        elements: Sequence[ElementIdLike],
        properties: Sequence[PropertyIdLike],
        property_names: Optional[Sequence[str]] = None,
    ) -> BatchResult[dict[str, str | tapir.ErrorItem]]:
        """Read display strings into per-element dictionaries, retaining nested errors."""
        keys = (
            list(property_names)
            if property_names
            else [str(normalize_property_id(p).propertyId.guid) for p in properties]
        )
        raw = self._get_raw_property_values(elements, properties)
        return BatchResult.from_items(
            raw,
            accessor=lambda el: dict(zip(keys, _extract_property_values(el))),
            root_key="elements",
        )

    def get_property_values_dict_per_element(
        self,
        elements: Sequence[ElementIdLike],
        properties: Sequence[PropertyIdLike],
        property_names: Optional[Sequence[str]] = None,
    ) -> list[dict[str, str]]:
        """Read per-element dictionaries of display strings; raise on reported failures."""
        res = self.get_property_values_dict_per_element_result(elements, properties, property_names)
        res.raise_for_errors("Property dictionary read")
        return res.successes

    def set_property_values_per_element_result(
        self,
        elements: Sequence[ElementIdLike],
        properties: Sequence[PropertyIdLike],
        values_matrix: Sequence[Sequence[Any]],
    ) -> BatchResult[list[tapir.SuccessfulExecutionResult | tapir.FailedExecutionResult]]:
        """Write display values, returning one execution-result row per element.

        Each row contains one success or failure per requested property. Partial
        failures are retained; successful writes are not rolled back by this helper.
        Values follow create_element_property_values conversion rules.
        """
        n_props = len(properties)
        payload = create_element_property_values(elements, properties, values_matrix)
        raw_res = self._api.tapir.property.set_property_values_of_elements(payload)
        grouped = [raw_res[i * n_props : (i + 1) * n_props] for i in range(len(elements))]
        return BatchResult.from_items(grouped, root_key="elements")

    def set_property_values_per_element(
        self,
        elements: Sequence[ElementIdLike],
        properties: Sequence[PropertyIdLike],
        values_matrix: Sequence[Sequence[Any]],
    ) -> int:
        """Write an N x M matrix of display values; raise on any reported failure.

        Returns the count of written property values when all succeed. Errors are
        checked after the batch executes; successful writes are not rolled back by
        this helper when BatchOperationError is raised. This is not an atomic write.
        """
        res = self.set_property_values_per_element_result(elements, properties, values_matrix)
        res.raise_for_errors("Batch property values write")
        return len(elements) * len(properties)

    def set_flat_property_values_result(
        self,
        elements: Sequence[ElementIdLike],
        property_id: PropertyIdLike,
        values: Sequence[Any],
    ) -> BatchResult[tapir.SuccessfulExecutionResult]:
        """Write one property, retaining per-element success and failure results.

        Values follow create_element_property_values_flat conversion rules.
        Successful writes are not rolled back by this helper on partial failure.
        """
        payload = create_element_property_values_flat(elements, property_id, values)
        raw_res = self._api.tapir.property.set_property_values_of_elements(payload)
        return BatchResult.from_items(raw_res, root_key="executionResults")

    def set_flat_property_values(
        self,
        elements: Sequence[ElementIdLike],
        property_id: PropertyIdLike,
        values: Sequence[Any],
    ) -> int:
        """Write one property across elements; raise on any reported failure.

        Returns the count of written property values when all succeed. Errors are
        checked after the batch executes; successful writes are not rolled back by
        this helper when BatchOperationError is raised. This is not an atomic write.
        """
        res = self.set_flat_property_values_result(elements, property_id, values)
        res.raise_for_errors("Single property write")
        return len(res.successes)

    def get_property_details_result(
        self, properties: Sequence[PropertyIdLike]
    ) -> BatchResult[official.PropertyDefinition]:
        """Diagnostic metadata lookup returning a BatchResult container."""
        property_definitions = self._api.official.property.get_details_of_properties(
            [to_official_property_id(p) for p in properties]
        )
        return BatchResult.from_items(
            property_definitions, accessor=lambda item: item.propertyDefinition, root_key="propertyDefinitions"
        )

    def get_property_details(self, properties: Sequence[PropertyIdLike]) -> list[official.PropertyDefinition]:
        """Fail-fast metadata lookup returning a clean list of PropertyDefinition models."""
        res = self.get_property_details_result(properties)
        res.raise_for_errors("Property details inspection")
        return res.successes

    def get_property_types_result(self, properties: Sequence[PropertyIdLike]) -> BatchResult[str]:
        """Diagnostic data type names lookup returning a BatchResult container."""
        return self.get_property_details_result(properties).map(lambda d: d.type)

    def get_property_types(self, properties: Sequence[PropertyIdLike]) -> list[str]:
        """Fail-fast data type names lookup returning a clean list of type name strings."""
        res = self.get_property_types_result(properties)
        res.raise_for_errors("Property types inspection")
        return res.successes
