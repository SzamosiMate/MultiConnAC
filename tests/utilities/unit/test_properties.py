from __future__ import annotations

from unittest.mock import MagicMock
import uuid
import pytest

from multiconn_archicad.utilities.properties import (
    create_element_property_values,
    create_element_property_values_flat,
    get_flat_property_values,
    get_possible_enum_values,
    get_property_details,
    get_property_types,
    get_property_values_dict_per_element,
    get_property_values_per_element,
    resolve_property_ids,
    set_element_property_values,
    set_flat_property_values,
)
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir


@pytest.fixture
def mock_api():
    """Mock UnifiedApi without spec restrictions to allow dynamic .official and .tapir access."""
    return MagicMock()


# ==============================================================================
# Property ID Resolution Tests
# ==============================================================================


def test_resolve_property_ids_success_and_error(mock_api):
    guid = uuid.uuid4()
    mock_api.official.property.get_property_ids.return_value = [
        official.PropertyIdArrayItem(propertyId=official.PropertyId(guid=guid)),
        official.ErrorItem(error=official.Error(code=1, message="Property not found")),
    ]

    result = resolve_property_ids(mock_api, [("Dimensions", "Height"), ("Non", "Existent")])

    assert result.is_all_success is False
    assert result.has_errors is True
    assert len(result.items) == 2
    assert result.items[0] == tapir.PropertyIdArrayItem(propertyId=tapir.PropertyId(guid=guid))
    assert result.items[1] is None
    assert result.errors[1].code == 1


# ==============================================================================
# Batch Reading & Unwrapping Tests
# ==============================================================================


def test_get_property_values_per_element_2d_matrix(mock_api):
    elem1, elem2 = uuid.uuid4(), uuid.uuid4()
    prop1, prop2 = uuid.uuid4(), uuid.uuid4()

    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-01")),
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="2800")),
        ]),
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-02")),
            tapir.ErrorItem(error=tapir.Error(code=2, message="Not evaluated")),
        ]),
    ]

    result = get_property_values_per_element(mock_api, [elem1, elem2], [prop1, prop2])

    assert result.is_all_success is True  # Batch of elements succeeded
    assert result.items[0] == ["Wall-01", "2800"]
    assert result.items[1] == ["Wall-02", None]  # Inner property error unwrapped to None


def test_get_property_values_per_element_with_element_error(mock_api):
    elem1, elem2 = uuid.uuid4(), uuid.uuid4()
    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.ErrorItem(error=tapir.Error(code=404, message="Element deleted")),
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Column-01")),
        ]),
    ]

    result = get_property_values_per_element(mock_api, [elem1, elem2], [uuid.uuid4()])

    assert result.is_all_success is False
    assert result.items[0] is None
    assert result.errors[0].code == 404
    assert result.items[1] == ["Column-01"]


def test_get_flat_property_values(mock_api):
    elem1, elem2 = uuid.uuid4(), uuid.uuid4()
    prop = uuid.uuid4()

    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Slab-01")),
        ]),
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Slab-02")),
        ]),
    ]

    result = get_flat_property_values(mock_api, [elem1, elem2], prop)
    assert result.items == ["Slab-01", "Slab-02"]


def test_get_property_values_dict_per_element(mock_api):
    elem = uuid.uuid4()
    prop1, prop2 = uuid.uuid4(), uuid.uuid4()

    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="W-01")),
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Concrete")),
        ]),
    ]

    # Explicit names
    result = get_property_values_dict_per_element(mock_api, [elem], [prop1, prop2], property_names=["ID", "Material"])
    assert result.items[0] == {"ID": "W-01", "Material": "Concrete"}

    # Default names fallback to GUID strings
    result_default = get_property_values_dict_per_element(mock_api, [elem], [prop1, prop2])
    assert result_default.items[0] == {str(prop1): "W-01", str(prop2): "Concrete"}


# ==============================================================================
# Batch Writing & Payload Builders Tests
# ==============================================================================


def test_create_element_property_values_2d():
    elems = [uuid.uuid4(), uuid.uuid4()]
    props = [uuid.uuid4(), uuid.uuid4()]
    matrix = [["A1", "B1"], ["A2", "B2"]]

    payload = create_element_property_values(elems, props, matrix)
    assert len(payload) == 4
    assert payload[0].propertyValue.value == "A1"
    assert payload[1].propertyValue.value == "B1"
    assert payload[2].propertyValue.value == "A2"
    assert payload[3].propertyValue.value == "B2"


def test_create_element_property_values_flat():
    elems = [uuid.uuid4(), uuid.uuid4()]
    prop = uuid.uuid4()
    values = ["Val1", "Val2"]

    payload = create_element_property_values_flat(elems, prop, values)
    assert len(payload) == 2
    assert payload[0].propertyValue.value == "Val1"
    assert payload[1].propertyValue.value == "Val2"


def test_set_element_property_values_masked_results(mock_api):
    payload = [
        tapir.ElementPropertyValue(
            elementId=tapir.ElementId(guid=uuid.uuid4()),
            propertyId=tapir.PropertyId(guid=uuid.uuid4()),
            propertyValue=tapir.PropertyValue(value="Test"),
        ),
        tapir.ElementPropertyValue(
            elementId=tapir.ElementId(guid=uuid.uuid4()),
            propertyId=tapir.PropertyId(guid=uuid.uuid4()),
            propertyValue=tapir.PropertyValue(value="Locked"),
        ),
    ]

    mock_api.tapir.property.set_property_values_of_elements.return_value = MagicMock(
        executionResults=[
            tapir.SuccessfulExecutionResult(success=True),
            tapir.FailedExecutionResult(success=False, error=tapir.Error(code=500, message="Element is locked")),
        ]
    )

    result = set_element_property_values(mock_api, payload)

    assert result.is_all_success is False
    assert result.items[0] == payload[0]  # Succeeded payload preserved
    assert result.items[1] is None        # Failed padded with None
    assert result.errors[1].code == 500


def test_set_flat_property_values(mock_api):
    elem = uuid.uuid4()
    prop = uuid.uuid4()
    mock_api.tapir.property.set_property_values_of_elements.return_value = MagicMock(
        executionResults=[tapir.SuccessfulExecutionResult(success=True)]
    )

    result = set_flat_property_values(mock_api, [elem], prop, ["NewVal"])
    assert result.is_all_success is True
    assert result.items[0].propertyValue.value == "NewVal"


# ==============================================================================
# Metadata & Inspection Tests
# ==============================================================================


def test_get_property_details_and_types(mock_api):
    prop1, prop2 = uuid.uuid4(), uuid.uuid4()

    mock_prop_def_1 = MagicMock(type="string", description="Test string")
    mock_prop_def_2 = MagicMock(type="integer", description="Test int")

    mock_api.official.property.get_details_of_properties.return_value = [
        MagicMock(propertyDefinition=mock_prop_def_1),
        MagicMock(propertyDefinition=mock_prop_def_2),
    ]

    details_res = get_property_details(mock_api, [prop1, prop2])
    assert details_res.items == [mock_prop_def_1, mock_prop_def_2]

    types_res = get_property_types(mock_api, [prop1, prop2])
    assert types_res.items == ["string", "integer"]


def test_get_possible_enum_values():
    prop_def = official.PropertyDefinition(
        group=official.PropertyGroup(
            propertyGroupId=official.PropertyGroupId(guid=uuid.uuid4()),
            name="GENERAL RATINGS",
        ),
        name="Fire Resistance Rating",
        description="minutes",
        isEditable=True,
        type="singleEnum",
        possibleEnumValues=[
            official.PossibleEnumValuesArrayItem(
                enumValue=official.PossibleEnumValue(
                    enumValueId=official.DisplayValueEnumId(displayValue="20 minutes"),
                    displayValue="20 minutes",
                )
            ),
            official.PossibleEnumValuesArrayItem(
                enumValue=official.PossibleEnumValue(
                    enumValueId=official.DisplayValueEnumId(displayValue="30 minutes"),
                    displayValue="30 minutes",
                )
            ),
        ],
    )

    assert get_possible_enum_values(prop_def) == ["20 minutes", "30 minutes"]


def test_get_possible_enum_values_non_enum_returns_empty():
    prop_def = official.PropertyDefinition(
        group=official.PropertyGroup(
            propertyGroupId=official.PropertyGroupId(guid=uuid.uuid4()),
            name="Window/Door",
        ),
        name="W/D Opening Opening Volume",
        description="",
        isEditable=False,
        type="volume",
        possibleEnumValues=None,
    )

    assert get_possible_enum_values(prop_def) == []