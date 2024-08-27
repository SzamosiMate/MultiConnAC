from conn_header import *
from port import Port
from actions import *
import asyncio
import aiohttp


class MultiConn:
    base_url: str = "http://127.0.0.1"
    port_range: range = range(19723, 19744)

    def __init__(self):
        self.open_port_headers: dict[Port, ConnHeader] = {}
        self.refresh()
        # load actions
        self.connect: Connect = Connect(self)
        self.connect_or_open: ConnectOrOpen = ConnectOrOpen(self)
        self.disconnect: Disconnect = Disconnect(self)
        self.quit_and_disconnect: QuitAndDisconnect = QuitAndDisconnect(self)
        self.run_async: RunAsync = RunAsync(self)

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
            if self.open_port_headers[port].ProductInfo is APIResponseError:
                await self.open_port_headers[port].get_product_info()
            if self.open_port_headers[port].ArchiCadID is APIResponseError:
                await self.open_port_headers[port].get_archicad_id()

    async def close_if_open(self, port: Port) -> None:
        if port in self.open_port_headers.keys():
            self.open_port_headers.pop(port)

    async def check_port(self, session: aiohttp.ClientSession, port: Port) -> None:
        url = f"{self.base_url}:{port}"
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
            tasks = [self.check_port(session, Port(port)) for port in self.port_range]
            await asyncio.gather(*tasks)

    def refresh(self) -> None:
        asyncio.run(self.scan_ports())


if __name__ == "__main__":
    conn = MultiConn()

    conn.open_port_headers[Port(19723)].port = Port(19727)
    conn.connect.all()
    print(conn.active)
    print(conn.failed)
    print(conn.pending)
    conn.open_port_headers[Port(19723)].port = Port(19723)
    conn.connect.failed()
    print(conn.active)
    print(conn.failed)
    print(conn.pending)





