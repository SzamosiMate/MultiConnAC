import json
from typing import Any
import aiohttp
from  port import Port
import asyncio
import functools

def sync_or_async(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            if asyncio.get_event_loop().is_running():
                return func(*args, **kwargs)
        except RuntimeError:
            pass
        return asyncio.run(func(*args, **kwargs))
    return wrapper

class CoreCommands:

    _BASE_URL: str = "http://127.0.0.1"

    def __init__(self, port: Port = 19723):
        self.port = port

    @sync_or_async
    async def post_command(self, command: str, parameters: dict | None = None) -> dict[str, Any]:
        if parameters is None:
            parameters = {}
        url = f"{self._BASE_URL:}:{self.port}"
        json_str = json.dumps({"command": command,
                               "parameters": parameters}).encode("utf8")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json.loads(json_str)) as response:
                result = await response.text()
                return json.loads(result)

    @sync_or_async
    async def post_tapir_command(self, command: str, parameters: dict | None = None) -> dict[str, Any]:
        if parameters is None:
            parameters = {}
        return await self.post_command(
                command="API.ExecuteAddOnCommand",
                parameters={"addOnCommandId": {
                                "commandNamespace": 'TapirCommand',
                                "commandName": command},
                            'addOnCommandParameters': parameters})


