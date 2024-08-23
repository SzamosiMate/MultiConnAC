from conn_header import *
from port import Port
from actions import actions
import asyncio
import aiohttp
import importlib


class MultiConn:
    base_url = "http://127.0.0.1"
    port_range = range(19723, 19744)

    def __init__(self):
        self.open_ports: dict[Port: ConnHeader] = {}
        self.active: dict[Port: ConnHeader] = {}
        self.inactive: dict[Port: ConnHeader] = {}
        asyncio.run(self.scan_ports())
        self.actions = {}
        self.load_actions()

    async def check_port(self, session: aiohttp.ClientSession, port: int) -> None:
        url = f"{self.base_url}:{port}"
        try:
            async with session.get(url, timeout=1) as response:
                if response.status == 200:
                    print(f"Port {port} is active.")
                    self.open_ports[port] = await ConnHeader.async_init(port)
                    self.inactive[port] = self.open_ports[port]
                    print(f"Getting conn header for port {port}")
                else:
                    print(f"Port {port} is inactive.")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            print(f"Port {port} is raises exception")

    async def scan_ports(self) -> None:
        async with aiohttp.ClientSession() as session:
            tasks = [self.check_port(session, port) for port in self.port_range]
            await asyncio.gather(*tasks)

    def load_actions(self):
        for module_name, class_name in actions.items():
            module = importlib.import_module(f'actions.{module_name}')
            action_class = getattr(module, class_name)
            action_instance = action_class(self)
            self.actions[class_name] = action_instance

    def __getattr__(self, item):
        # Allow access to command instances via multi_conn.<module_name>
        return self.actions.get(item, None)


if __name__ == "__main__":
    conn = MultiConn()
    print(conn.active)
    conn.Connect.from_ports(19723)
    print(conn.active)

    print(conn.open_ports)

