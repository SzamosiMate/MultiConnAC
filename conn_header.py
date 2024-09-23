from core_commands import  CoreCommands
from basic_types import ArchiCadID, APIResponseError, ProductInfo, create_object_or_error_from_response
import asyncio
from enum import Enum
from port import Port
from archicad_connection import ArchiCADConnection
from typing import Self

class Status(Enum):
    PENDING: str = 'pending'
    ACTIVE: str = 'active'
    FAILED: str = 'failed'
    UNASSIGNED: str = 'unassigned'

class ConnHeader:

    def __init__(self, port: Port, initialize: bool = True):
        self.port: Port = port
        self.status: Status = Status.PENDING
        self.core = CoreCommands(self.port)
        self.ac = ArchiCADConnection(self.port)

        if initialize:
            self.ProductInfo: ProductInfo | APIResponseError = asyncio.run(self.get_product_info())
            self.ArchiCadID: ArchiCadID | APIResponseError = asyncio.run(self.get_archicad_id())

    @classmethod
    async def async_init(cls, port: Port) -> Self:
        instance = cls(port, initialize=False)
        instance.ProductInfo = await instance.get_product_info()
        instance.ArchiCadID = await instance.get_archicad_id()
        return instance

    def connect(self) -> None:
        if isinstance(self.ProductInfo, APIResponseError):
            self.ProductInfo = asyncio.run(self.get_product_info())
        if isinstance(self.ProductInfo, ProductInfo):
            self.ac.connect(self.ProductInfo)
            self.status = Status.ACTIVE
        else:
            self.status = Status.FAILED

    def disconnect(self) -> None:
        self.ac.disconnect()
        self.status = Status.PENDING

    async def get_product_info(self) -> ProductInfo | APIResponseError:
        result = await self.core.post_command(command="API.GetProductInfo")
        return await create_object_or_error_from_response(result, ProductInfo)

    async def get_archicad_id(self) -> ArchiCadID | APIResponseError:
        result = await self.core.post_tapir_command(command='GetProjectInfo')
        return await create_object_or_error_from_response(result, ArchiCadID)

