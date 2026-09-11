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
from multiconn_archicad.utilities.results import BatchResult, BatchResult2D, extract_error

if TYPE_CHECKING:
    from multiconn_archicad.clients.unified_api.api import UnifiedApi


def _extract_property_value(item: tapir.PropertyValueArrayItem) -> str:
    return item.propertyValue.value


def _single_property_item(element: tapir.PropertyValuesArrayItem) -> tapir.PropertyValueArrayItem | tapir.ErrorItem:
    if len(element.propertyValues) != 1:
        raise ValueError(f"Single property lookup row returned {len(element.propertyValues)} values; expected 1.")
    return element.propertyValues[0]


def _require_length(items: Sequence[Any], expected: int, response_name: str) -> None:
    if len(items) != expected:
        raise ValueError(f"{response_name} returned {len(items)} item(s); expected {expected}.")


def _to_prop_value(val: Any) -> tapir.PropertyValue:
    return val if isinstance(val, tapir.PropertyValue) else tapir.PropertyValue(value="" if val is None else str(val))


def create_element_property_values(
    elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike], values_matrix: Sequence[Sequence[Any]]
) -> list[tapir.ElementPropertyValue]:
    """Build an N x M payload using display strings.

    PropertyValue models pass through; None becomes an empty string and other
    values use str(value). No numeric formatting or unit conversion is performed.
    Typed API errors are rejected before conversion.
    """
    norm_elements = normalize_element_ids(elements)
    norm_props = normalize_property_ids(properties)
    if len(norm_elements) != len(values_matrix):
        raise ValueError(f"Expected {len(norm_elements)} rows in values_matrix, got {len(values_matrix)}.")
    BatchResult2D.from_rows(values_matrix, row_lengths=[len(norm_props)] * len(norm_elements)).raise_for_errors(
        "Property write input"
    )

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
    Typed API errors are rejected before conversion.
    """
    pid = normalize_property_id(property_id).propertyId
    if len(elements) != len(values):
        raise ValueError(f"Expected {len(elements)} rows in values, got {len(values)}.")
    BatchResult.from_items(values).raise_for_errors("Property write input")
    return [
        tapir.ElementPropertyValue(elementId=e.elementId, propertyId=pid, propertyValue=_to_prop_value(v))
        for e, v in zip(normalize_element_ids(elements), values)
    ]


def create_element_property_values_from_coords(
    elements: Sequence[ElementIdLike],
    properties: Sequence[PropertyIdLike],
    coordinates: Sequence[tuple[int, int]],
    values: Sequence[Any],
) -> list[tapir.ElementPropertyValue]:
    """Build a sparse property-value payload from explicit element/property coordinates."""
    if len(coordinates) != len(values):
        raise ValueError("coordinates and values must have the same length.")
    normalized_elements = normalize_element_ids(elements)
    normalized_properties = normalize_property_ids(properties)
    seen: set[tuple[int, int]] = set()
    normalized_coordinates: list[tuple[int, int]] = []
    for coordinate in coordinates:
        if not isinstance(coordinate, Sequence) or isinstance(coordinate, (str, bytes)) or len(coordinate) != 2:
            raise ValueError("Every coordinate must contain an element and property index.")
        element_index, property_index = coordinate
        if not isinstance(element_index, int) or not isinstance(property_index, int):
            raise TypeError("Property-value coordinates must contain integer indices.")
        normalized_coordinate = (element_index, property_index)
        if (
            element_index < 0
            or element_index >= len(normalized_elements)
            or property_index < 0
            or property_index >= len(normalized_properties)
        ):
            raise IndexError("Property-value coordinate is out of bounds.")
        if normalized_coordinate in seen:
            raise ValueError("Duplicate property-value coordinate.")
        seen.add(normalized_coordinate)
        normalized_coordinates.append(normalized_coordinate)
    BatchResult.from_items(values).raise_for_errors("Property write input")
    return [
        tapir.ElementPropertyValue(
            elementId=normalized_elements[element_index].elementId,
            propertyId=normalized_properties[property_index].propertyId,
            propertyValue=_to_prop_value(value),
        )
        for (element_index, property_index), value in zip(normalized_coordinates, values)
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
        raw = self._api.official.property.get_property_ids(list(property_user_ids))
        _require_length(raw, len(property_user_ids), "Property ID lookup")
        return BatchResult.from_items(raw, accessor=normalize_property_id)

    def resolve_property_ids(self, property_user_ids: Sequence[PropertyUserId]) -> list[tapir.PropertyIdArrayItem]:
        """Fail-fast batch lookup returning a clean list of Tapir PropertyId models."""
        res = self.resolve_property_ids_result(property_user_ids)
        res.raise_for_errors("Property ID resolution")
        return list(res.successes)

    def resolve_property_id(self, property_user_id: PropertyUserId) -> tapir.PropertyIdArrayItem:
        """Scalar convenience: resolves a single property identifier or raises."""
        return self.resolve_property_ids([property_user_id])[0]

    def get_property_values_per_element_result(
        self, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
    ) -> BatchResult2D[str]:
        """Read display strings: one row per element, with nested ErrorItems on failure."""
        items = self._get_raw_property_values(elements, properties)
        _require_length(items, len(elements), "Property values lookup")
        rows = [item if extract_error(item) else item.propertyValues for item in items]
        return BatchResult2D.from_rows(
            rows, row_lengths=[len(properties)] * len(elements), accessor=_extract_property_value
        )

    def get_property_values_per_element(
        self, elements: Sequence[ElementIdLike], properties: Sequence[PropertyIdLike]
    ) -> list[list[str]]:
        """Read an N x M matrix of display strings; raise on any reported failure.

        Values are not parsed as numbers or converted to standard units.
        """
        res = self.get_property_values_per_element_result(elements, properties)
        res.raise_for_errors("Batch property values read")
        values_by_row: list[list[str]] = [[] for _ in elements]
        for (row_index, _), value in res.iter_successes():
            values_by_row[row_index].append(value)
        return values_by_row

    def get_flat_property_values_result(
        self, elements: Sequence[ElementIdLike], property_id: PropertyIdLike
    ) -> BatchResult[str]:
        """Read one property as display strings, retaining per-element failures."""
        property_values = self._get_raw_property_values(elements, [property_id])
        _require_length(property_values, len(elements), "Single property lookup")
        items = [item if extract_error(item) else _single_property_item(item) for item in property_values]
        return BatchResult.from_items(items, accessor=_extract_property_value)

    def get_flat_property_values(self, elements: Sequence[ElementIdLike], property_id: PropertyIdLike) -> list[str]:
        """Read one property as display strings; raise on any reported failure.

        Values are not parsed as numbers or converted to standard units.
        """
        res = self.get_flat_property_values_result(elements, property_id)
        res.raise_for_errors("Single property read")
        return list(res.successes)

    def get_property_values_dict_per_element(
        self,
        elements: Sequence[ElementIdLike],
        properties: Sequence[PropertyIdLike],
        property_names: Optional[Sequence[str]] = None,
    ) -> list[dict[str, str]]:
        """Read complete property rows into dictionaries, failing before partial rows escape."""
        keys = (
            list(property_names)
            if property_names is not None
            else [str(normalize_property_id(p).propertyId.guid) for p in properties]
        )
        if len(keys) != len(properties):
            raise ValueError("property_names length must match properties length.")
        res = self.get_property_values_per_element_result(elements, properties)
        res.raise_for_errors("Property dictionary read")
        values_by_row: list[list[str]] = [[] for _ in elements]
        for (row_index, _), value in res.iter_successes():
            values_by_row[row_index].append(value)
        return [dict(zip(keys, values)) for values in values_by_row]

    def set_property_values_per_element_result(
        self,
        elements: Sequence[ElementIdLike],
        properties: Sequence[PropertyIdLike],
        values_matrix: Sequence[Sequence[Any]],
    ) -> BatchResult2D[tapir.SuccessfulExecutionResult]:
        """Write display values, returning one execution-result row per element.

        Each row contains one success or failure per requested property. Partial
        failures are retained; successful writes are not rolled back by this helper.
        Values follow create_element_property_values conversion rules.
        """
        n_props = len(properties)
        payload = create_element_property_values(elements, properties, values_matrix)
        raw_res = self._api.tapir.property.set_property_values_of_elements(payload)
        _require_length(raw_res, len(elements) * len(properties), "Property values write")
        grouped = [raw_res[i * n_props : (i + 1) * n_props] for i in range(len(elements))]
        return BatchResult2D.from_rows(grouped, row_lengths=[n_props] * len(elements))

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
        _require_length(raw_res, len(elements), "Single property write")
        return BatchResult.from_items(raw_res)

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
        _require_length(property_definitions, len(properties), "Property details lookup")
        return BatchResult.from_items(property_definitions, accessor=lambda item: item.propertyDefinition)

    def get_property_details(self, properties: Sequence[PropertyIdLike]) -> list[official.PropertyDefinition]:
        """Fail-fast metadata lookup returning a clean list of PropertyDefinition models."""
        res = self.get_property_details_result(properties)
        res.raise_for_errors("Property details inspection")
        return list(res.successes)

    def get_property_types_result(self, properties: Sequence[PropertyIdLike]) -> BatchResult[str]:
        """Diagnostic data type names lookup returning a BatchResult container."""
        return self.get_property_details_result(properties).map(lambda d: d.type)

    def get_property_types(self, properties: Sequence[PropertyIdLike]) -> list[str]:
        """Fail-fast data type names lookup returning a clean list of type name strings."""
        res = self.get_property_types_result(properties)
        res.raise_for_errors("Property types inspection")
        return list(res.successes)
