from dataclasses import dataclass
from typing import Self, Protocol, TypeVar, Type

class FromAPIResponse(Protocol):
    @classmethod
    def from_api_response(cls, response: dict) -> Self:
        ...

@dataclass
class ProductInfo:
    version: int
    build: int
    lang: str

    @classmethod
    def from_api_response(cls, response: dict) -> Self:
         return cls(response["result"]["version"],
                    response["result"]["buildNumber"],
                    response["result"]["languageCode"])


@dataclass
class ArchiCadID:
    isUntitled: bool
    isTeamwork: bool
    projectLocation: str | None = None
    projectPath: str | None = None
    projectName: str = 'Untitled'

    @classmethod
    def from_api_response(cls, response: dict) -> Self:
        addon_command_response = response['result']['addOnCommandResponse']
        if addon_command_response['isUntitled']:
            return cls(isUntitled=addon_command_response['isUntitled'],
                       isTeamwork=addon_command_response['isTeamwork'])
        else:
            return cls(isUntitled=addon_command_response['isUntitled'],
                       isTeamwork=addon_command_response['isTeamwork'],
                       projectLocation=addon_command_response['projectLocation'],
                       projectPath=addon_command_response['projectPath'],
                       projectName=addon_command_response['projectName'])

@dataclass
class APIResponseError:
    code: int
    message: str

    @classmethod
    def from_api_response(cls, response: dict) -> Self:
        return cls(code=response['error']['code'],
                   message=response['error']['message'])


T = TypeVar('T', bound='FromAPIResponse')

async def create_object_or_error_from_response(result: dict, class_to_create: Type[T]) -> T | APIResponseError:
    if result["succeeded"]:
        return class_to_create.from_api_response(result)
    else:
        return APIResponseError.from_api_response(result)
