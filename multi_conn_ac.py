from conn_header import *
from port import Port
from actions import Action, ActionRegistry
import asyncio
import aiohttp


class MultiConn:
    base_url: str = "http://127.0.0.1"
    port_range: range = range(19723, 19744)

    def __init__(self):
        self.available_port_headers: dict[Port: ConnHeader] = {}
        asyncio.run(self.scan_ports())
        self.actions: dict[str, Action] = {}
        self.load_actions()

    @property
    def pending(self) -> dict[Port: ConnHeader]:
        return self.get_all_port_headers_with_status(Status.PENDING)

    @property
    def active(self) -> dict[Port: ConnHeader]:
        return self.get_all_port_headers_with_status(Status.ACTIVE)

    @property
    def failed(self) -> dict[Port: ConnHeader]:
        return self.get_all_port_headers_with_status(Status.FAILED)

    def get_all_port_headers_with_status(self, status: Status) -> dict[Port: ConnHeader]:
        return [conn_header for conn_header in self.available_port_headers.values() if conn_header.status == status]

    async def check_port(self, session: aiohttp.ClientSession, port: Port) -> None:
        url = f"{self.base_url}:{port}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=1)) as response:
                if response.status == 200:
                    print(f"Port {port} is active.")
                    self.available_port_headers[port] = await ConnHeader.async_init(port)
                    print(f"Getting conn header for port {port}")
                else:
                    print(f"Port {port} is inactive.")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            print(f"Port {port} is raises exception")

    async def scan_ports(self) -> None:
        async with aiohttp.ClientSession() as session:
            tasks = [self.check_port(session, Port(port)) for port in self.port_range]
            await asyncio.gather(*tasks)

    def load_actions(self) -> None:
        for class_name, action_class in ActionRegistry.get_commands().items():
            action_instance = action_class(self)
            self.actions[class_name] = action_instance

    def __getattr__(self, item) -> Action:
        # Allow access to action instances via multi_conn.<class_name>
        return self.actions[item] if item in self.actions else self.__getattribute__(item)


if __name__ == "__main__":
    conn = MultiConn()
    print(conn.active)
    conn.Connect.from_ports(Port(19723))
    print(conn.active)

    print(conn.available_port_headers)

