from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Union
from uuid import UUID

from multiconn_archicad.models.official import types as official
from multiconn_archicad.models.tapir import types as tapir

# ==============================================================================
# Liberal Input Type Aliases
# ==============================================================================

ElementIdLike = Union[
    tapir.ElementIdArrayItem,
    official.ElementIdArrayItem,
    tapir.ElementId,
    official.ElementId,
    str,
    UUID,
]

PropertyIdLike = Union[
    tapir.PropertyIdArrayItem,
    official.PropertyIdArrayItem,
    tapir.PropertyId,
    official.PropertyId,
    str,
    UUID,
]

PropertyUserIdLike = Union[
    official.UserDefinedPropertyUserId,
    official.BuiltInPropertyUserId,
    tuple[str, str],
]


# ==============================================================================
# Identifier Normalizers
# ==============================================================================


def _to_uuid(val: str | UUID) -> UUID:
    return val if isinstance(val, UUID) else UUID(str(val).strip())


def normalize_element_id(element: ElementIdLike) -> tapir.ElementIdArrayItem:
    """Coerces any element identifier format into a Tapir ElementIdArrayItem."""
    if isinstance(element, tapir.ElementIdArrayItem):
        return element
    if isinstance(element, official.ElementIdArrayItem):
        return tapir.ElementIdArrayItem(elementId=tapir.ElementId(guid=element.elementId.guid))
    if isinstance(element, (tapir.ElementId, official.ElementId)):
        return tapir.ElementIdArrayItem(elementId=tapir.ElementId(guid=element.guid))
    if isinstance(element, (UUID, str)):
        return tapir.ElementIdArrayItem(elementId=tapir.ElementId(guid=_to_uuid(element)))
    raise TypeError(f"Unsupported element ID type: {type(element)!r}")


def normalize_element_ids(elements: Sequence[ElementIdLike]) -> list[tapir.ElementIdArrayItem]:
    return [normalize_element_id(e) for e in elements]


def normalize_property_id(property_id: PropertyIdLike) -> tapir.PropertyIdArrayItem:
    """Coerces any property identifier format into a Tapir PropertyIdArrayItem."""
    if isinstance(property_id, tapir.PropertyIdArrayItem):
        return property_id
    if isinstance(property_id, official.PropertyIdArrayItem):
        return tapir.PropertyIdArrayItem(propertyId=tapir.PropertyId(guid=property_id.propertyId.guid))
    if isinstance(property_id, (tapir.PropertyId, official.PropertyId)):
        return tapir.PropertyIdArrayItem(propertyId=tapir.PropertyId(guid=property_id.guid))
    if isinstance(property_id, (UUID, str)):
        return tapir.PropertyIdArrayItem(propertyId=tapir.PropertyId(guid=_to_uuid(property_id)))
    raise TypeError(f"Unsupported property ID type: {type(property_id)!r}")


def normalize_property_ids(properties: Sequence[PropertyIdLike]) -> list[tapir.PropertyIdArrayItem]:
    return [normalize_property_id(p) for p in properties]


def to_official_property_id(property_id: PropertyIdLike) -> official.PropertyIdArrayItem:
    """Converts any property ID to an Official PropertyIdArrayItem."""
    if isinstance(property_id, official.PropertyIdArrayItem):
        return property_id
    guid = normalize_property_id(property_id).propertyId.guid
    return official.PropertyIdArrayItem(propertyId=official.PropertyId(guid=guid))


def normalize_property_user_id(user_id: PropertyUserIdLike) -> official.UserDefinedPropertyUserId | official.BuiltInPropertyUserId:
    """Coerces a (group, name) tuple or typed user ID to an Official PropertyUserId."""
    if isinstance(user_id, (official.UserDefinedPropertyUserId, official.BuiltInPropertyUserId)):
        return user_id
    if isinstance(user_id, (tuple, list)):
        if len(user_id) != 2:
            raise ValueError(f"Property user ID tuple must contain exactly (group, name), got {user_id!r}")
        return official.UserDefinedPropertyUserId(type="UserDefined", localizedName=[str(user_id[0]), str(user_id[1])])
    raise TypeError(f"Unsupported property user ID type: {type(user_id)!r}")


def split_builtin_name(non_localized_name: str) -> tuple[str, str]:
    """Splits a BuiltIn property name like 'General_ID' into ('General', 'ID')."""
    match = re.search(r"(.+?(?=_))_(.+)", non_localized_name)
    if not match:
        raise ValueError(f"BuiltIn name '{non_localized_name}' cannot be split (missing '_' separator).")
    return match.group(1), match.group(2)
