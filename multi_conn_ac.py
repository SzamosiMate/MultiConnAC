from conn_header import *
from port import Port
from actions import *
import asyncio
import aiohttp


class MultiConn:
    _base_url: str = "http://127.0.0.1"
    _port_range: range = range(19723, 19744)

    def __init__(self):
        self.open_port_headers: dict[Port, ConnHeader] = {}
        self.refresh()
        # load actions
        self.connect: Connect = Connect(self)
        self.disconnect: Disconnect = Disconnect(self)
        self.run_command: RunCommand = RunCommand(self)


    @property
    def pending(self) -> dict[Port, ConnHeader]:
        return self.get_all_port_headers_with_status(Status.PENDING)

    @property
    def active(self) -> dict[Port, ConnHeader]:
        return self.get_all_port_headers_with_status(Status.ACTIVE)

    @property
    def failed(self) -> dict[Port, ConnHeader]:
        return self.get_all_port_headers_with_status(Status.FAILED)

    def get_all_port_headers_with_status(self, status: Status) -> dict[Port, ConnHeader]:
        return {conn_header.port: conn_header
                for conn_header in self.open_port_headers.values()
                if conn_header.status == status}

    async def create_or_refresh_connection(self, port: Port) -> None:
        if port not in self.open_port_headers.keys():
            self.open_port_headers[port] = await ConnHeader.async_init(port)
        else:
            if isinstance(self.open_port_headers[port].ProductInfo, APIResponseError):
                await self.open_port_headers[port].get_product_info()
            if isinstance(self.open_port_headers[port].ArchiCadID, APIResponseError):
                await self.open_port_headers[port].get_archicad_id()

    async def close_if_open(self, port: Port) -> None:
        if port in self.open_port_headers.keys():
            self.open_port_headers.pop(port)

    async def check_port(self, session: aiohttp.ClientSession, port: Port) -> None:
        url = f"{self._base_url}:{port}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=1)) as response:
                if response.status == 200:
                    await self.create_or_refresh_connection(port)
                else:
                    await self.close_if_open(port)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            await self.close_if_open(port)
            print(f"Port {port} is raises exception")

    async def scan_ports(self) -> None:
        async with aiohttp.ClientSession() as session:
            tasks = [self.check_port(session, Port(port)) for port in self._port_range]
            await asyncio.gather(*tasks)

    def refresh(self) -> None:
        asyncio.run(self.scan_ports())









