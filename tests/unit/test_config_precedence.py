from pydantic import BaseModel, ConfigDict, ValidationError
import pytest

from tests.utilities import run_in_process


# =========================================================================
# TIER 1: Baseline Defaults
# =========================================================================

@run_in_process
def test_tier_1_baseline_defaults_apply_when_no_mixins():
    """
    Proves that without mixins:
    1. Baseline extra="ignore" silently drops unknown fields.
    2. Baseline populate_by_name=True and serialize_by_alias=True are active.
    """
    from multiconn_archicad.models.base import APIModel
    from multiconn_archicad.models.tapir.types import Coordinate2D

    assert APIModel.model_config.get("extra") == "ignore"
    assert APIModel.model_config.get("populate_by_name") is True
    assert APIModel.model_config.get("serialize_by_alias") is True

    coord = Coordinate2D.model_validate({"x": 10.0, "y": 20.0, "extra_ignored_key": "xyz"})
    assert coord.x == 10.0
    assert coord.y == 20.0
    assert not hasattr(coord, "extra_ignored_key")


# =========================================================================
# TIER 2: Mixin Overrides Baseline Config
# =========================================================================

@run_in_process
def test_tier_2_mixin_overrides_baseline_and_preserves_other_defaults():
    """
    Proves that injecting ForbidExtrasMixin:
    1. Overrides baseline extra="ignore" -> extra="forbid".
    2. Preserves other non-conflicting baseline defaults (populate_by_name, serialize_by_alias).
    """
    from multiconn_archicad.models.config import configure
    from multiconn_archicad.models.mixins import ForbidExtrasMixin

    configure(ForbidExtrasMixin)

    from multiconn_archicad.models.base import APIModel
    from multiconn_archicad.models.tapir.types import Coordinate2D

    assert APIModel.model_config.get("extra") == "forbid"
    assert APIModel.model_config.get("populate_by_name") is True
    assert APIModel.model_config.get("serialize_by_alias") is True

    with pytest.raises(ValidationError) as exc_info:
        Coordinate2D.model_validate({"x": 1.0, "y": 2.0, "forbidden_extra": 123})

    assert any(err["type"] == "extra_forbidden" for err in exc_info.value.errors())


# =========================================================================
# TIER 3: Concrete Model Overrides Both Base and Mixin
# =========================================================================

@run_in_process
def test_tier_3_concrete_model_overrides_mixin():
    """
    Proves that a leaf model with an explicit ConfigDict (e.g. extra="allow"):
    1. Overrides the mixin's extra="forbid".
    2. Overrides the baseline's extra="ignore".
    """
    from multiconn_archicad.models.config import configure
    from multiconn_archicad.models.mixins import ForbidExtrasMixin

    configure(ForbidExtrasMixin)

    from multiconn_archicad.models.base import APIModel
    from multiconn_archicad.models.official.types import AddOnCommandParameters
    from multiconn_archicad.models.tapir.types import Coordinate2D

    class CustomPermissiveModel(APIModel):
        model_config = ConfigDict(extra="allow")
        name: str

    with pytest.raises(ValidationError):
        Coordinate2D(x=1.0, y=2.0, extra_key="fails")

    custom = CustomPermissiveModel(name="test", arbitrary_dynamic_field=999)
    assert custom.name == "test"
    assert getattr(custom, "arbitrary_dynamic_field") == 999

    addon_params = AddOnCommandParameters.model_validate({
        "archicadCustomPayload": {"guid": "123-abc"},
        "speedMultiplier": 1.5,
    })
    dumped = addon_params.model_dump()
    assert dumped["archicadCustomPayload"] == {"guid": "123-abc"}
    assert dumped["speedMultiplier"] == 1.5


# =========================================================================
# COMPLETE HIERARCHY: Multi-Mixin Composition + Overrides
# =========================================================================

@run_in_process
def test_full_precedence_hierarchy_with_multiple_mixins():
    """
    Proves the full stack in action simultaneously:
    - Baseline: populate_by_name=True
    - Mixin 1 (ForbidExtrasMixin): extra="forbid"
    - Mixin 2 (FrozenMixin): frozen=True
    - Mixin 3 (StrictMixin): strict=True
    - Leaf Model: overrides extra="allow" and frozen=False
    """
    from multiconn_archicad.models.config import configure
    from multiconn_archicad.models.mixins import ForbidExtrasMixin, FrozenMixin, StrictMixin

    configure(ForbidExtrasMixin, FrozenMixin, StrictMixin)

    from multiconn_archicad.models.base import APIModel
    from multiconn_archicad.models.tapir.types import Coordinate2D

    assert APIModel.model_config.get("populate_by_name") is True
    assert APIModel.model_config.get("extra") == "forbid"
    assert APIModel.model_config.get("frozen") is True
    assert APIModel.model_config.get("strict") is True

    coord = Coordinate2D(x=1.0, y=2.0)