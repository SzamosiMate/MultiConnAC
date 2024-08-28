import json
from typing import Any
from dataclasses import dataclass
import asyncio
import aiohttp
from enum import Enum, auto
from port import Port
from connection_builder import ConnectionBuilder

class Status(Enum):
    PENDING: int = auto()
    ACTIVE: int = auto()
    FAILED: int = auto()
    UNASSIGNED: int = auto()


@dataclass
class ProductInfo:
    version: int
    build: int
    lang: str


@dataclass
class ArchiCadID:
    isUntitled: bool
    isTeamwork: bool
    projectLocation: str | None = None
    projectPath: str | None = None
    projectName: str = 'Untitled'


@dataclass
class APIResponseError:
    code: int
    message: str


class ConnHeader:

    base_url: str = "http://127.0.0.1"

    def __init__(self, port: Port, initialize: bool = True):
        self.port: Port = port
        self.status: Status = Status.PENDING
        self.types = ConnectionBuilder.base_types
        self.commands = ConnectionBuilder.base_commands
        self.utilities = ConnectionBuilder.base_utilities

        if initialize:
            self.ProductInfo: ProductInfo | APIResponseError = asyncio.run(self.get_product_info())
            self.ArchiCadID: ArchiCadID | APIResponseError = asyncio.run(self.get_archicad_id())

    @classmethod
    async def async_init(cls, port: Port):
        instance = cls(port, initialize=False)
        instance.ProductInfo = await instance.get_product_info()
        instance.ArchiCadID = await instance.get_archicad_id()
        return instance

    def connect(self) -> None:

        def build_connection() -> None:
            c_builder = ConnectionBuilder(self.port, self.ProductInfo)
            print(f' the type of commands before: {type(self.commands)}')
            print(f' the type of cb before: {type(c_builder)}')
            self.types = c_builder.types
            self.commands = c_builder.commands
            self.utilities = c_builder.utilities
            print(f' the type of commands after: {type(self.commands)}')
            print(f'c_builder.commands: {c_builder.commands}')

        if isinstance(self.ProductInfo, APIResponseError) :
            self.ProductInfo = asyncio.run(self.get_product_info())
        if isinstance(self.ProductInfo, ProductInfo):
            build_connection()
            self.status = Status.ACTIVE
        else:
            self.status = Status.FAILED

    def disconnect(self) -> None:
        self.types = ConnectionBuilder.base_types
        self.commands = ConnectionBuilder.base_commands
        self.utilities = ConnectionBuilder.base_utilities
        self.status = Status.PENDING

    async def post_command(self, port: Port, json_str: str) -> dict[str, Any]:
        url = f"{self.base_url}:{port}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json.loads(json_str)) as response:
                result = await response.text()
                return json.loads(result)

    async def get_product_info(self) -> ProductInfo | APIResponseError:
        result = await self.post_command(self.port, json.dumps({"command": "API.GetProductInfo"}))
        if result["succeeded"]:
            return ProductInfo(version=result["result"]["version"],
                               build=result["result"]["buildNumber"],
                               lang=result["result"]["languageCode"])
        else:
            return APIResponseError(code=result['error']['code'],
                                    message=result['error']['message'])

    async def get_archicad_id(self) -> ArchiCadID | APIResponseError:

        async def create_json_get_archicad_id() -> str:
            return json.dumps({
                "command": "API.ExecuteAddOnCommand",
                "parameters": {
                    "addOnCommandId": {
                        "commandNamespace": 'TapirCommand',
                        "commandName": "GetProjectInfo"
                    }
                }
            })

        async def create_archicad_id() -> ArchiCadID:
            addon_command_response = result['result']['addOnCommandResponse']
            if addon_command_response['isUntitled']:
                return ArchiCadID(isUntitled=addon_command_response['isUntitled'],
                                  isTeamwork=addon_command_response['isTeamwork'])
            else:
                return ArchiCadID(isUntitled=addon_command_response['isUntitled'],
                                  isTeamwork=addon_command_response['isTeamwork'],
                                  projectLocation=addon_command_response['projectLocation'],
                                  projectPath=addon_command_response['projectPath'],
                                  projectName=addon_command_response['projectName'])

        json_str = await create_json_get_archicad_id()
        result = await self.post_command(self.port, json_str)
        if result["succeeded"]:
            return await create_archicad_id()
        else:
            return APIResponseError(code=result['error']['code'],
                                    message=result['error']['message'])
