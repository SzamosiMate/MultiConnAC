from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from multiconn_archicad.errors import BatchOperationError
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir
from multiconn_archicad.utilities.properties import (
    PropertyUtilities,
    create_element_property_values,
    create_element_property_values_flat,
    create_element_property_values_from_coords,
    get_possible_enum_values,
)
from multiconn_archicad.utilities.results import BatchResult
from multiconn_archicad.utilities import BatchRun


def _value(value: str) -> tapir.PropertyValueArrayItem:
    return tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value=value))


def _error() -> tapir.ErrorItem:
    return tapir.ErrorItem(error=tapir.Error(code=7, message="bad"))


def test_payload_builders_and_sparse_coordinates_validate_shape_and_duplicates():
    elements, properties = [uuid4(), uuid4()], [uuid4(), uuid4()]
    assert len(create_element_property_values(elements, properties, [["a", None], [0, False]])) == 4
    assert len(create_element_property_values_flat(elements, properties[0], ["a", "b"])) == 2
    sparse = create_element_property_values_from_coords(elements, properties, [(1, 0)], ["x"])
    assert sparse[0].elementId.guid == elements[1]
    with pytest.raises(ValueError):
        create_element_property_values_from_coords(elements, properties, [(0, 0), (0, 0)], ["a", "b"])
    with pytest.raises(IndexError):
        create_element_property_values_from_coords(elements, properties, [(2, 0)], ["a"])


def test_matrix_read_preserves_cell_error_and_dictionary_is_fail_fast():
    api = MagicMock()
    api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[_value("a"), _error()])
    ]
    utilities = PropertyUtilities(api)
    result = utilities.get_property_values_per_element_result([uuid4()], [uuid4(), uuid4()])
    assert list(result.iter_errors())[0][0] == (0, 1)
    with pytest.raises(BatchOperationError):
        utilities.get_property_values_dict_per_element([uuid4()], [uuid4(), uuid4()], ["a", "b"])
    with pytest.raises(ValueError):
        utilities.get_property_values_dict_per_element([uuid4()], [uuid4()], ["a", "b"])


def test_row_error_and_partial_copy_pipeline_keep_other_cells_writable():
    api = MagicMock()
    elements, properties = [uuid4(), uuid4()], [uuid4(), uuid4()]
    api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[_value("a"), _error()]),
        _error(),
    ]
    read = PropertyUtilities(api).get_property_values_per_element_result(elements, properties)
    assert [coordinate for coordinate, _ in read.iter_errors()] == [(0, 1), (1, None)]
    run = BatchRun(elements)
    run.record("read", read)
    values, coordinates = read.flatten(skip_errors=True)
    payload = create_element_property_values_from_coords(elements, properties, coordinates, values)
    assert len(payload) == 1
    api.tapir.property.set_property_values_of_elements.return_value = [tapir.SuccessfulExecutionResult(success=True)]
    write = BatchResult.from_items(api.tapir.property.set_property_values_of_elements(payload))
    run.record("copy", write, item_indices=[row for row, _ in coordinates], details=coordinates)
    outcomes = run.finish()
    assert outcomes[0].failed
    assert outcomes[1].failed
    assert api.tapir.property.set_property_values_of_elements.call_count == 1


def test_property_response_cardinality_is_checked_before_result_conversion():
    api = MagicMock()
    api.tapir.property.get_property_values_of_elements.return_value = []
    utilities = PropertyUtilities(api)
    with pytest.raises(ValueError, match="returned 0"):
        utilities.get_flat_property_values_result([uuid4()], uuid4())
    api.tapir.property.set_property_values_of_elements.return_value = []
    with pytest.raises(ValueError, match="expected 1"):
        utilities.set_flat_property_values_result([uuid4()], uuid4(), ["x"])


def test_id_details_and_matrix_cardinality_checks_include_inner_rows():
    api = MagicMock()
    utilities = PropertyUtilities(api)
    user_id = official.UserDefinedPropertyUserId(localizedName=["Group", "Name"])
    api.official.property.get_property_ids.return_value = []
    with pytest.raises(ValueError, match="expected 1"):
        utilities.resolve_property_ids_result([user_id])
    api.official.property.get_details_of_properties.return_value = []
    with pytest.raises(ValueError, match="expected 1"):
        utilities.get_property_details_result([uuid4()])
    api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[_value("only")])
    ]
    with pytest.raises(ValueError, match="does not match"):
        utilities.get_property_values_per_element_result([uuid4()], [uuid4(), uuid4()])


def test_matrix_write_uses_2d_result_and_zero_property_cardinality():
    api = MagicMock()
    api.tapir.property.set_property_values_of_elements.return_value = []
    result = PropertyUtilities(api).set_property_values_per_element_result([uuid4()], [], [[]])
    assert result.row_lengths == (0,)
    assert result.is_all_success


def test_resolution_metadata_and_enum_helpers():
    api = MagicMock()
    guid = uuid4()
    api.official.property.get_property_ids.return_value = [
        official.PropertyIdArrayItem(propertyId=official.PropertyId(guid=guid))
    ]
    utilities = PropertyUtilities(api)
    user_id = official.UserDefinedPropertyUserId(localizedName=["Group", "Name"])
    assert utilities.resolve_property_id(user_id).propertyId.guid == guid
    definition = official.PropertyDefinition(
        group=official.PropertyGroup(propertyGroupId=official.PropertyGroupId(guid=uuid4()), name="G"),
        name="N",
        description="",
        isEditable=True,
        type="string",
        possibleEnumValues=None,
    )
    api.official.property.get_details_of_properties.return_value = [
        official.PropertyDefinitionWrapperItem(propertyDefinition=definition)
    ]
    assert utilities.get_property_types([guid]) == ["string"]
    assert get_possible_enum_values(definition) == []
