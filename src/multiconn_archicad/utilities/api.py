from __future__ import annotations

from typing import TYPE_CHECKING

from .properties import PropertyUtilities

if TYPE_CHECKING:
    from multiconn_archicad.clients.unified_api.api import UnifiedApi


class Utilities:
    """Domain groups of utility operations bound to one API instance."""

    def __init__(self, api: UnifiedApi):
        self.property = PropertyUtilities(api)
