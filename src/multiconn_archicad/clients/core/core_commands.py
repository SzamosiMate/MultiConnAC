from __future__ import annotations
import json
from typing import Any, TYPE_CHECKING
import httpx
import logging
import asyncio

from multiconn_archicad.constants import DEFAULT_HOST
from multiconn_archicad.errors import (
    CommandTimeoutError,
    APIConnectionError,
    InvalidResponseFormatError,
    RequestError,
    StandardAPIError,
    StandardCommandUnavailable,
    TapirCommandError,
    AddOnCommandUnavailable,
)
from multiconn_archicad.orchestration.basic_types import Port
from multiconn_archicad.orchestration.system.cli_parser import get_cli_args_once

if TYPE_CHECKING:
    from multiconn_archicad.clients.core.literal_commands import AddonCommandType, TapirCommandType


log = logging.getLogger(__name__)


class CoreCommands:
    def __init__(self, port: Port | None = None, host: str = DEFAULT_HOST):
        cli_args = get_cli_args_once()
        self.port: Port | None = port if port else (Port(cli_args.port)) if cli_args.port else None
        self.url: str = f"{cli_args.host if cli_args.host else host}:{self.port}"

    def __repr__(self) -> str:
        attrs = ", ".join(f"{k}={v!r}" for k, v in vars(self).items())
        return f"{self.__class__.__name__}({attrs})"

    def __str__(self) -> str:
        return self.__repr__()

    def post_command(
        self, command: AddonCommandType, parameters: dict | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Posts a standard Archicad JSON command"""
        payload = {"command": command, "parameters": parameters}
        log.debug(f"command: {command} parameters:\n {json.dumps(parameters, indent=4)}")

        response = self._post_command(payload, timeout)

        if response.get("succeeded"):
            response = response.get("result", {})
            log.debug(f"response: {json.dumps(response, indent=4)}")
        else:
            log.warning(f"response: {response}")
            message = response.get("error", {}).get("message", "no message")
            code = response.get("error", {}).get("code", None)
            code = int(code) if isinstance(code, (str, int)) else None
            if code == 2002:
                raise StandardCommandUnavailable(message=message)
            elif code == 4010:
                raise AddOnCommandUnavailable(message=message)
            else:
                raise StandardAPIError(code=code, message=message)
        return response

    def post_tapir_command(
        self, command: TapirCommandType, parameters: dict | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Posts a Tapir Add-On command"""
        response = self.post_command(
            command="API.ExecuteAddOnCommand",
            parameters={
                "addOnCommandId": {
                    "commandNamespace": "TapirCommand",
                    "commandName": command,
                },
                "addOnCommandParameters": parameters,
            },
            timeout=timeout,
        )

        response = response.get("addOnCommandResponse", {})
        if response.get("error"):
            log.warning(f"response: {response}")
            raise TapirCommandError(
                message=response.get("error", {}).get("message", "no message"),
                code=response.get("error", {}).get("code", None),
            )
        return response

    async def post_command_async(
        self, command: AddonCommandType, parameters: dict | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Asynchronous wrapper for post_command."""
        return await asyncio.to_thread(self.post_command, command, parameters, timeout)

    async def post_tapir_command_async(
        self, command: TapirCommandType, parameters: dict | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Asynchronous wrapper for post_tapir_command."""
        return await asyncio.to_thread(self.post_tapir_command, command, parameters, timeout)

    def _post_command(self, payload: dict, timeout: float | int | None) -> dict[str, Any]:
        command_name = payload.get("command")
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(self.url, json=payload, timeout=timeout)
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException as e:
            message = f"Command '{command_name}' to {self.url} timed out after {timeout} seconds."
            log.info(message)
            raise CommandTimeoutError(message) from e
        except httpx.RequestError as e:
            message = f"HTTP error for command '{command_name}' to {self.url}: {e}"
            log.error(message)
            raise APIConnectionError(message) from e
        except json.JSONDecodeError as e:
            message = "Failed to decode JSON response."
            log.error(message)
            raise InvalidResponseFormatError(message) from e
        except Exception as e:
            message = f"Unexpected error during post_command '{command_name}': {type(e).__name__} - {e}"
            log.exception(message)
            raise RequestError(message) from e
        return result
