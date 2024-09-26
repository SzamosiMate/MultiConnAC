from conn_header import *
from port import Port
from actions import *
import asyncio
import aiohttp
from typing import Callable, Any
from types import MethodType


class MultiConn:
    _base_url: str = "http://127.0.0.1"
    _port_range: range = range(19723, 19744)

    def __init__(self):
        self.open_port_headers: dict[Port, ConnHeader] = {}
        self.refresh()

        # load command namespaces for IDE typehints. Replaced at runtime.
        self.core = CoreCommands()
        self.archicad = ArchiCADConnection()

        # load actions
        self.connect: Connect = Connect(self)
        self.disconnect: Disconnect = Disconnect(self)


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

    def __getattribute__(self, attribute):
        if attribute in ["core", "archicad"]:
            return MultiConnProxy(self, [attribute])
        else:
            return super().__getattribute__(attribute)

    def refresh(self) -> None:
        asyncio.run(self.scan_ports())

    async def scan_ports(self) -> None:
        async with aiohttp.ClientSession() as session:
            tasks = [self.check_port(session, Port(port)) for port in self._port_range]
            await asyncio.gather(*tasks)

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


class MultiConnProxy:
    """A proxy to alter the intercepted method call. It will call the same
    method on all active ConnHeaders of the parent, with the provided attribute path"""

    def __init__(self, parent: MultiConn, attribute: list[str]):
        self.parent: MultiConn = parent
        self._attr_path: list[str] = attribute

    def __getattr__(self, item):
        """Capture further attribute accesses and extend the path."""
        self._attr_path.append(item)
        return self

    def __call__(self, *args, **kwargs):
        """When the chain ends with a callable, trigger `run_on_all_active`."""
        return self._run_on_all_active(self._attr_path, *args, **kwargs)

    def _run_on_all_active(self, attribute_path: list[str], *args, **kwargs) -> dict[Port, Any]:
        """Calls the same method on all active connections based on the attribute path.
        Args and kwargs with a 'port' key will be passed individually per port."""
        results = {}
        for port, conn_header in self.parent.active.items():
            function_to_run = self._get_bound_method_at_attribute_path(conn_header, attribute_path)

            port_args = self._get_port_specific_args(port, args)
            port_kwargs = self._get_port_specific_kwargs(port, kwargs)

            # Call the method with port-specific args and kwargs
            result = function_to_run(*port_args, **port_kwargs)
            results.update({port: result})
        return results

    @staticmethod
    def _get_bound_method_at_attribute_path(current_object: object, attribute_path: list[str]) -> Callable:
        assert len(attribute_path) > 0
        for attr in attribute_path:
            if not hasattr(current_object, attr):
                raise AttributeError(f"'{current_object.__class__.__name__}' object has no attribute '{attr}'")
            previous_object = current_object
            current_object = getattr(current_object, attr)
        # bind current_object (method) to previous_object instance
        return current_object.__get__(previous_object)

    @staticmethod
    def _get_port_specific_args(port: Port, args: tuple) -> list:
        """Extract args that are specific to the given port."""
        port_args = []
        for arg in args:
            if isinstance(arg, dict) and port in arg:
                port_args.append(arg[port])
            else:
                port_args.append(arg)  # If no port key, use the original argument
        return port_args

    @staticmethod
    def _get_port_specific_kwargs(port: Port, kwargs: dict) -> dict:
        """Extract kwargs that are specific to the given port."""
        port_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, dict) and port in value:
                port_kwargs[key] = value[port]
            else:
                port_kwargs[key] = value  # If no port key, use the original keyword argument
        return port_kwargs






