import json
from typing import Any
from dataclasses import dataclass
from archicad.connection import ACConnection   # type: ignore
from archicad.commands import UnsucceededCommandCall
import asyncio
import aiohttp
from port import Port
from enum import Enum, auto


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
        self.conn: ACConnection | None = None
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
        print('called')
        try:
            self.conn = ACConnection(self.port)
            print(f' conn is {self.conn}')
            if type(self.conn) is ACConnection:
                self.status = Status.ACTIVE
            else:
                self.status = Status.FAILED
        except Exception:
            self.status = Status.FAILED

    def disconnect(self) -> None:
        self.conn = None
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

    @staticmethod
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

    @staticmethod
    async def create_archicad_id(result) -> ArchiCadID:
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

    async def get_archicad_id(self) -> ArchiCadID | APIResponseError:
        json_str = await self.create_json_get_archicad_id()
        result = await self.post_command(self.port, json_str)
        if result["succeeded"]:
            return await self.create_archicad_id(result)
        else:
            return APIResponseError(code=result['error']['code'],
                                    message=result['error']['message'])
