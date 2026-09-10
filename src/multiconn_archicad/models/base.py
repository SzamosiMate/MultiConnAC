from typing import Any
from pydantic import BaseModel, ConfigDict
from .config import _Registry

_DEFAULT_CONFIG: dict[str, Any] = {
    "extra": "ignore",
    "populate_by_name": True,
    "serialize_by_alias": True,
    "allow_inf_nan": False,
}

_merged_config = dict(_DEFAULT_CONFIG)
for mixin in _Registry.mixins:
    if hasattr(mixin, "model_config"):
        _merged_config.update(mixin.model_config)

_bases = _Registry.mixins + (BaseModel,)


class APIModel(*_bases):
    """A custom base model for the Unified API"""

    model_config = ConfigDict(**_merged_config)

    def model_dump(
        self,
        *,
        by_alias: bool = True,
        exclude_none: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return super().model_dump(
            by_alias=by_alias,
            exclude_none=exclude_none,
            **kwargs,
        )

    def model_dump_json(
        self,
        *,
        by_alias: bool = True,
        exclude_none: bool = True,
        **kwargs: Any,
    ) -> str:
        return super().model_dump_json(
            by_alias=by_alias,
            exclude_none=exclude_none,
            **kwargs,
        )


# =====================================================================
# LOCK CONFIGURATION
# =====================================================================
_Registry.locked = True