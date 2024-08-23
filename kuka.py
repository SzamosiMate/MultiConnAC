from archicad.connection import ACConnection, create_request
from archicad.commands import BasicCommands, UnsucceededCommandCall, post_command
import json


def get_all_ports() -> tuple[list[int], list[BasicCommands]]:
    open_ports, basic_commands = [], []
    for port in ACConnection._port_range():
        req = create_request(port)
        basic_command = BasicCommands(req)
        try:
            print("Trying:" + str(port))
            result = post_command(req, json.dumps({"command": "API.GetProductInfo"}))
            print(result)
            result = post_command(req, json.dumps({
                "command": "API.ExecuteAddOnCommand",
                "parameters": {
                    "addOnCommandId": {
                        "commandNamespace": 'TapirCommand',
                        "commandName": "GetProjectInfo"
                    }
                }
            }))
            print(result)
            basic_command.IsAlive()
            open_ports.append(port)
            basic_commands.append(basic_command)
            print("I found one!" + str(port))
        except Exception:
            continue
    return open_ports, basic_commands


get_all_ports()
