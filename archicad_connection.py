from __future__ import annotations
from typing import TYPE_CHECKING
from port import Port
if TYPE_CHECKING:
    from conn_header import ProductInfo


from archicad.versioning import _Versioning
from archicad.connection import create_request
from archicad.releases import Commands, Types, Utilities


class ArchiCADConnection:
    types = Types
    commands = Commands
    utilities = Utilities

    def __init__(self, port: Port = Port(19723)):
        self._request = create_request(int(port))

    def connect(self, product_info: ProductInfo) -> None:
        v = _Versioning(product_info.version, product_info.build, self._request)
        self.commands = v.commands
        self.types = v.types
        self.utilities = v.utilities

    def disconnect(self) -> None:
        self.types = Types
        self.commands = Commands
        self.utilities = Utilities