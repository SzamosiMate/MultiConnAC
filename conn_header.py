import json
from typing import Any
from dataclasses import dataclass
from archicad.connection import ACConnection, create_request
import asyncio
import aiohttp

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

    base_url = "http://127.0.0.1"

    def __init__(self, port: int, initialize: bool = True):
        self.port: int = port
        self.conn: ACConnection | None = None
        if initialize:
            self.ProductInfo: ProductInfo | APIResponseError = asyncio.run(self.get_product_info())
            self.ArchiCadID: ArchiCadID | APIResponseError = asyncio.run(self.get_archicad_id())

    def connect(self) -> None:
        self.conn = ACConnection(self.port)

    def disconnect(self) -> None:
        self.conn = None

    @classmethod
    async def async_init(cls, port: int):
        instance = cls(port, initialize=False)
        instance.ProductInfo = await instance.get_product_info()
        instance.ArchiCadID = await instance.get_archicad_id()
        return instance

    async def post_command(self, port: int, json_str: str) -> dict[str, Any]:
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
