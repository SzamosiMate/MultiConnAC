from __future__ import annotations

import uuid
import pytest

from multiconn_archicad.utilities.identifiers import (
    normalize_element_id,
    normalize_element_ids,
    normalize_property_id,
    normalize_property_ids,
    normalize_property_user_id,
    split_builtin_name,
    to_official_property_id,
)
from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir


# ==============================================================================
# Element ID Normalization Tests
# ==============================================================================


def test_normalize_element_id_from_all_types():
    raw_guid = uuid.uuid4()
    str_guid = str(raw_guid)

    # 1. From string
    res_str = normalize_element_id(str_guid)
    assert isinstance(res_str, tapir.ElementIdArrayItem)
    assert res_str.elementId.guid == raw_guid

    # 2. From UUID
    res_uuid = normalize_element_id(raw_guid)
    assert res_uuid.elementId.guid == raw_guid

    # 3. From Tapir ElementId
    res_tapir_elem = normalize_element_id(tapir.ElementId(guid=raw_guid))
    assert res_tapir_elem.elementId.guid == raw_guid

    # 4. From Tapir ElementIdArrayItem
    item = tapir.ElementIdArrayItem(elementId=tapir.ElementId(guid=raw_guid))
    assert normalize_element_id(item) is item

    # 5. From Official ElementIdArrayItem
    official_item = official.ElementIdArrayItem(elementId=official.ElementId(guid=raw_guid))
    res_off = normalize_element_id(official_item)
    assert isinstance(res_off, tapir.ElementIdArrayItem)
    assert res_off.elementId.guid == raw_guid


def test_normalize_element_id_invalid_type_raises():
    with pytest.raises(TypeError, match="Unsupported element ID type"):
        normalize_element_id(12345)  # type: ignore


def test_normalize_element_ids_bulk():
    guids = [uuid.uuid4(), str(uuid.uuid4())]
    results = normalize_element_ids(guids)
    assert len(results) == 2
    assert all(isinstance(x, tapir.ElementIdArrayItem) for x in results)


# ==============================================================================
# Property ID Normalization Tests
# ==============================================================================


def test_normalize_property_id_from_all_types():
    raw_guid = uuid.uuid4()
    str_guid = str(raw_guid)

    # From string & UUID
    assert normalize_property_id(str_guid).propertyId.guid == raw_guid
    assert normalize_property_id(raw_guid).propertyId.guid == raw_guid

    # From Tapir model (identity check)
    tapir_item = tapir.PropertyIdArrayItem(propertyId=tapir.PropertyId(guid=raw_guid))
    assert normalize_property_id(tapir_item) is tapir_item

    # From Official model
    official_item = official.PropertyIdArrayItem(propertyId=official.PropertyId(guid=raw_guid))
    res = normalize_property_id(official_item)
    assert isinstance(res, tapir.PropertyIdArrayItem)
    assert res.propertyId.guid == raw_guid


def test_normalize_property_id_invalid_type_raises():
    with pytest.raises(TypeError, match="Unsupported property ID type"):
        normalize_property_id({"guid": str(uuid.uuid4())})  # type: ignore


def test_to_official_property_id():
    raw_guid = uuid.uuid4()
    official_item = official.PropertyIdArrayItem(propertyId=official.PropertyId(guid=raw_guid))

    # Existing official item returns unchanged
    assert to_official_property_id(official_item) is official_item

    # Tapir item converts to official
    tapir_item = tapir.PropertyIdArrayItem(propertyId=tapir.PropertyId(guid=raw_guid))
    converted = to_official_property_id(tapir_item)
    assert isinstance(converted, official.PropertyIdArrayItem)
    assert converted.propertyId.guid == raw_guid


# ==============================================================================
# Property User ID & Name Splitting Tests
# ==============================================================================


def test_normalize_property_user_id():
    # From tuple
    uid_tuple = ("Dimensions", "Height")
    res_tuple = normalize_property_user_id(uid_tuple)
    assert isinstance(res_tuple, official.UserDefinedPropertyUserId)
    assert res_tuple.localizedName == ["Dimensions", "Height"]

    # From Official models (idempotent)
    ud = official.UserDefinedPropertyUserId(type="UserDefined", localizedName=["Custom", "Prop"])
    bi = official.BuiltInPropertyUserId(type="BuiltIn", nonLocalizedName="General_ID")
    assert normalize_property_user_id(ud) is ud
    assert normalize_property_user_id(bi) is bi


def test_normalize_property_user_id_invalid():
    with pytest.raises(ValueError, match="must contain exactly"):
        normalize_property_user_id(("SingleElement",))  # type: ignore

    with pytest.raises(TypeError, match="Unsupported property user ID type"):
        normalize_property_user_id(123)  # type: ignore


def test_split_builtin_name():
    group, name = split_builtin_name("General_ID")
    assert group == "General"
    assert name == "ID"

    # Multi-underscore split on first occurrence
    group, name = split_builtin_name("Composite_Wall_Thickness")
    assert group == "Composite"
    assert name == "Wall_Thickness"

    with pytest.raises(ValueError, match="cannot be split"):
        split_builtin_name("NoSeparatorHere")