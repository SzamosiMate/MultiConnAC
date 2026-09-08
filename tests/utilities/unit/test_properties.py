from __future__ import annotations

from unittest.mock import MagicMock
import uuid
import pytest

from multiconn_archicad.utilities.properties import (
    create_element_property_values,
    create_element_property_values_flat,
    get_flat_property_values,
    get_flat_property_values_result,
    get_possible_enum_values,
    get_property_details,
    get_property_details_result,
    get_property_types,
    get_property_types_result,
    get_property_values_dict_per_element,
    get_property_values_dict_per_element_result,
    get_property_values_per_element,
    get_property_values_per_element_result,
    resolve_property_id,
    resolve_property_ids,
    resolve_property_ids_result,
    set_flat_property_values,
    set_flat_property_values_result,
    set_property_values_per_element,
    set_property_values_per_element_result,
)
from multiconn_archicad.utilities.results import BatchOperationError
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir


@pytest.fixture
def mock_api():
    """Mock UnifiedApi without spec restrictions to allow dynamic .official and .tapir access."""
    return MagicMock()


# ==============================================================================
# Property ID Resolution Tests
# ==============================================================================


def test_resolve_property_ids_result_success_and_error(mock_api):
    guid = uuid.uuid4()
    err_item = official.ErrorItem(error=official.Error(code=1, message="Property not found"))
    mock_api.official.property.get_property_ids.return_value = [
        official.PropertyIdArrayItem(propertyId=official.PropertyId(guid=guid)),
        err_item,
    ]

    result = resolve_property_ids_result(mock_api, [("Dimensions", "Height"), ("Non", "Existent")])

    assert result.is_all_success is False
    assert result.has_errors is True
    assert len(result.items) == 2
    assert result.items[0] == tapir.PropertyIdArrayItem(propertyId=tapir.PropertyId(guid=guid))
    assert result.items[1] == err_item
    assert result.errors[1][0].code == 1
    assert result.errors[1][0].path == "propertyIds[1]"


def test_resolve_property_ids_fail_fast_success(mock_api):
    guid1, guid2 = uuid.uuid4(), uuid.uuid4()
    mock_api.official.property.get_property_ids.return_value = [
        official.PropertyIdArrayItem(propertyId=official.PropertyId(guid=guid1)),
        official.PropertyIdArrayItem(propertyId=official.PropertyId(guid=guid2)),
    ]

    resolved = resolve_property_ids(mock_api, [("Group", "Prop1"), ("Group", "Prop2")])
    assert len(resolved) == 2
    assert resolved[0].propertyId.guid == guid1
    assert resolved[1].propertyId.guid == guid2


def test_resolve_property_ids_fail_fast_raises_on_error(mock_api):
    mock_api.official.property.get_property_ids.return_value = [
        official.ErrorItem(error=official.Error(code=404, message="Property not found")),
    ]

    with pytest.raises(BatchOperationError) as exc_info:
        resolve_property_ids(mock_api, [("Group", "Missing")])

    assert "Property ID resolution failed with 1 error(s) across 1 item(s):" in str(exc_info.value)
    assert exc_info.value.result.has_errors is True


def test_resolve_property_id_scalar(mock_api):
    guid = uuid.uuid4()
    mock_api.official.property.get_property_ids.return_value = [
        official.PropertyIdArrayItem(propertyId=official.PropertyId(guid=guid)),
    ]

    prop = resolve_property_id(mock_api, ("Dimensions", "Height"))
    assert prop.propertyId.guid == guid


def test_resolve_property_id_scalar_raises_on_error(mock_api):
    mock_api.official.property.get_property_ids.return_value = [
        official.ErrorItem(error=official.Error(code=404, message="Not found")),
    ]

    with pytest.raises(BatchOperationError):
        resolve_property_id(mock_api, ("Missing", "Prop"))


# ==============================================================================
# Batch Reading Tests
# ==============================================================================


def test_get_property_values_per_element_result_success(mock_api):
    elem1, elem2 = uuid.uuid4(), uuid.uuid4()
    prop1, prop2 = uuid.uuid4(), uuid.uuid4()

    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-01")),
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="2800")),
        ]),
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-02")),
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="3000")),
        ]),
    ]

    res = get_property_values_per_element_result(mock_api, [elem1, elem2], [prop1, prop2])
    assert res.is_all_success is True
    assert res.items == [["Wall-01", "2800"], ["Wall-02", "3000"]]


def test_get_property_values_per_element_result_inner_property_error(mock_api):
    elem1 = uuid.uuid4()
    err_item = tapir.ErrorItem(error=tapir.Error(code=2, message="Not evaluated"))
    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Wall-01")),
            err_item,
        ]),
    ]

    res = get_property_values_per_element_result(mock_api, [elem1], [uuid.uuid4(), uuid.uuid4()])
    assert res.is_all_success is False
    assert res.items[0] == ["Wall-01", err_item]  # Raw ErrorItem retained inside the row
    assert res.errors[0][0].code == 2
    assert res.errors[0][0].message == "Not evaluated"
    assert res.errors[0][0].path == "elements[0].propertyValues[1]"


def test_get_property_values_per_element_fail_fast_raises_on_inner_property_error(mock_api):
    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.ErrorItem(error=tapir.Error(code=2, message="Property not applicable")),
        ]),
    ]

    with pytest.raises(BatchOperationError) as exc_info:
        get_property_values_per_element(mock_api, [uuid.uuid4()], [uuid.uuid4()])

    assert "Batch property values read failed with 1 error(s) across 1 item(s):" in str(exc_info.value)
    assert "- elements[0].propertyValues[0]: [2] Property not applicable" in str(exc_info.value)


def test_get_flat_property_values_fail_fast_success(mock_api):
    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Slab-01")),
        ]),
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Slab-02")),
        ]),
    ]

    values = get_flat_property_values(mock_api, [uuid.uuid4(), uuid.uuid4()], uuid.uuid4())
    assert values == ["Slab-01", "Slab-02"]


def test_get_flat_property_values_fail_fast_raises_on_error(mock_api):
    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.ErrorItem(error=tapir.Error(code=5, message="Expression failed")),
        ]),
    ]

    with pytest.raises(BatchOperationError) as exc_info:
        get_flat_property_values(mock_api, [uuid.uuid4()], uuid.uuid4())

    assert "Single property read failed with 1 error(s) across 1 item(s):" in str(exc_info.value)


def test_get_property_values_dict_per_element_fail_fast_success(mock_api):
    mock_api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="W-01")),
            tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value="Concrete")),
        ]),
    ]

    result = get_property_values_dict_per_element(
        mock_api, [uuid.uuid4()], [uuid.uuid4(), uuid.uuid4()], property_names=["ID", "Material"]
    )
    assert result == [{"ID": "W-01", "Material": "Concrete"}]


# ==============================================================================
# Batch Writing & Mutation Tests (Using Masking & Filtering)
# ==============================================================================


def test_set_property_values_per_element_result_and_masking(mock_api):
    elem1, elem2 = uuid.uuid4(), uuid.uuid4()
    elems = [elem1, elem2]
    props = [uuid.uuid4()]
    matrix = [["V1"], ["V2"]]

    err_exec = tapir.FailedExecutionResult(success=False, error=tapir.Error(code=500, message="Locked"))
    # Mock returns the unwrapped list directly
    mock_api.tapir.property.set_property_values_of_elements.return_value = [
        tapir.SuccessfulExecutionResult(success=True),
        err_exec,
    ]

    res = set_property_values_per_element_result(mock_api, elems, props, matrix)

    assert res.is_all_success is False
    assert len(res.items) == 2
    assert res.items[1] == err_exec
    assert res.errors[1][0].code == 500
    assert res.errors[1][0].path == "executionResults[1]"

    # Test correlation to input parameters
    assert res.success_mask(elems) == [elem1, None]
    assert res.failure_mask(elems) == [None, elem2]
    assert res.filter_successful(elems) == [elem1]
    assert res.filter_failed(elems) == [elem2]


def test_set_property_values_per_element_fail_fast_success(mock_api):
    elems = [uuid.uuid4()]
    props = [uuid.uuid4(), uuid.uuid4()]
    matrix = [["V1", "V2"]]

    # Mock returns the unwrapped list directly
    mock_api.tapir.property.set_property_values_of_elements.return_value = [
        tapir.SuccessfulExecutionResult(success=True),
        tapir.SuccessfulExecutionResult(success=True),
    ]

    count = set_property_values_per_element(mock_api, elems, props, matrix)
    assert count == 2


def test_set_property_values_per_element_fail_fast_raises(mock_api):
    elems = [uuid.uuid4()]
    props = [uuid.uuid4()]
    matrix = [["V1"]]

    mock_api.tapir.property.set_property_values_of_elements.return_value = [
        tapir.FailedExecutionResult(success=False, error=tapir.Error(code=500, message="Locked")),
    ]

    with pytest.raises(BatchOperationError) as exc_info:
        set_property_values_per_element(mock_api, elems, props, matrix)

    assert "Batch property values write failed with 1 error(s) across 1 item(s):" in str(exc_info.value)


def test_set_flat_property_values_fail_fast(mock_api):
    elems = [uuid.uuid4()]
    prop = uuid.uuid4()
    # Mock returns the unwrapped list directly
    mock_api.tapir.property.set_property_values_of_elements.return_value = [
        tapir.SuccessfulExecutionResult(success=True)
    ]

    count = set_flat_property_values(mock_api, elems, prop, ["NewVal"])
    assert count == 1


# ==============================================================================
# Metadata & Inspection Tests
# ==============================================================================


def test_get_property_details_and_result(mock_api):
    prop = uuid.uuid4()
    mock_prop_def = MagicMock(type="string", description="Test string")
    # Mock returns unwrapped PropertyDefinition directly
    mock_api.official.property.get_details_of_properties.return_value = [
        mock_prop_def,
    ]

    res = get_property_details_result(mock_api, [prop])
    assert res.items == [mock_prop_def]

    details = get_property_details(mock_api, [prop])
    assert details == [mock_prop_def]


def test_get_property_types_and_result(mock_api):
    prop1, prop2 = uuid.uuid4(), uuid.uuid4()
    mock_prop_def_1 = MagicMock(type="string")
    mock_prop_def_2 = MagicMock(type="integer")

    # Mock returns unwrapped PropertyDefinitions directly
    mock_api.official.property.get_details_of_properties.return_value = [
        mock_prop_def_1,
        mock_prop_def_2,
    ]

    res = get_property_types_result(mock_api, [prop1, prop2])
    assert res.items == ["string", "integer"]

    types_list = get_property_types(mock_api, [prop1, prop2])
    assert types_list == ["string", "integer"]


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
        ],
    )

    assert get_possible_enum_values(prop_def) == ["20 minutes"]


def test_get_possible_enum_values_non_enum_returns_empty():
    prop_def = official.PropertyDefinition(
        group=official.PropertyGroup(
            propertyGroupId=official.PropertyGroupId(guid=uuid.uuid4()),
            name="Window/Door",
        ),
        name="Volume",
        description="",
        isEditable=False,
        type="volume",
        possibleEnumValues=None,
    )

    assert get_possible_enum_values(prop_def) == []