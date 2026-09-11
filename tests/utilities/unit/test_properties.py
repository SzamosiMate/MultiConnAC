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
    create_element_property_values_sparse,
    get_possible_enum_values,
)
from multiconn_archicad.utilities.results import BatchResult, BatchResult2D
from multiconn_archicad.utilities import BatchRun


def _value(value: str) -> tapir.PropertyValueArrayItem:
    return tapir.PropertyValueArrayItem(propertyValue=tapir.PropertyValue(value=value))


def _error() -> tapir.ErrorItem:
    return tapir.ErrorItem(error=tapir.Error(code=7, message="bad"))


def test_payload_builders_and_sparse_matrix_omit_failed_cells():
    elements, properties = [uuid4(), uuid4()], [uuid4(), uuid4()]
    assert len(create_element_property_values(elements, properties, [["a", None], [0, False]])) == 4
    assert len(create_element_property_values_flat(elements, properties[0], ["a", "b"])) == 2
    sparse = create_element_property_values_sparse(elements, properties, [[_error(), "x"], ["y", _error()]])
    assert len(sparse) == 2
    assert sparse[0].elementId.guid == elements[0]
    assert sparse[1].elementId.guid == elements[1]

    matrix = BatchResult2D.from_rows([["a", _error()], _error()], row_lengths=[2, 2])
    sparse_from_result = create_element_property_values_sparse(elements, properties, matrix)
    assert len(sparse_from_result) == 1
    assert sparse_from_result[0].elementId.guid == elements[0]


def test_matrix_read_preserves_cell_error_and_dictionary_aggregates_failed_rows():
    api = MagicMock()
    api.tapir.property.get_property_values_of_elements.return_value = [
        tapir.PropertyValuesArrayItem(propertyValues=[_error(), _error()]),
        tapir.PropertyValuesArrayItem(propertyValues=[_value("b"), _value("c")]),
    ]
    utilities = PropertyUtilities(api)
    elements, properties = [uuid4(), uuid4()], [uuid4(), uuid4()]
    result = utilities.get_property_values_per_element_result(elements, properties)
    assert list(result.iter_errors())[0][0] == (0, 0)

    dictionary_result = utilities.get_property_values_dict_per_element_result(elements, properties, ["a", "b"])
    assert dictionary_result.successes == [{"a": "b", "b": "c"}]
    assert len(dictionary_result.errors[0].causes) == 2
    assert "contains 2 error(s)" in dictionary_result.errors[0].message
    with pytest.raises(BatchOperationError):
        utilities.get_property_values_dict_per_element(elements, properties, ["a", "b"])
    with pytest.raises(ValueError):
        utilities.get_property_values_dict_per_element(elements, properties, ["a"])


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
    coordinates = read.coordinates()
    payload = create_element_property_values_sparse(elements, properties, read)
    assert len(payload) == 1
    api.tapir.property.set_property_values_of_elements.return_value = [tapir.SuccessfulExecutionResult(success=True)]
    write = BatchResult.from_items(api.tapir.property.set_property_values_of_elements(payload))
    run.record("copy", write, item_indices=[row for row, _ in coordinates], details=coordinates)
    report = run.finish()
    assert report.outcomes[0].failed
    assert report.outcomes[1].failed
    assert api.tapir.property.set_property_values_of_elements.call_count == 1


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
