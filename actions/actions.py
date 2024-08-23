from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from port import Port
from conn_header import *

if TYPE_CHECKING:
    from multi_conn_ac import MultiConn


class Action(ABC):
    def __init__(self, multi_conn):
        self.multi_conn: MultiConn = multi_conn

    def from_ports(self, *args: Port) -> None:
        self.execute_action([self.multi_conn.open_ports[port] for port in args if port in self.multi_conn.open_ports.keys()])

    def from_headers(self, *args: ConnHeader) -> None:
        self.execute_action([*args])

    def all(self) -> None:
        self.execute_action(list(self.multi_conn.open_ports.values()))

    @abstractmethod
    def execute_action(self, conn_headers: list[ConnHeader]) -> None:
        pass
