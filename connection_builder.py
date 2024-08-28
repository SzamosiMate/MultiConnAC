from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from conn_header import ProductInfo
    from port import Port

from archicad.versioning import _Versioning
from archicad.connection import create_request
from archicad.releases import Commands, Types, Utilities


class ConnectionBuilder:
    base_types = Types
    base_commands = Commands
    base_utilities = Utilities

    def __init__(self, port: Port, product_info: ProductInfo):
        self.request = create_request(int(port))
        v = _Versioning(product_info.version, product_info.build, self.request)
        self.commands = v.commands
        self.types = v.types
        self.utilities = v.utilities