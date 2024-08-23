from .actions import *


class Disconnect(Action):

    def execute_action(self, conn_headers: list[ConnHeader]) -> None:
        for conn_header in conn_headers:
            conn_header.disconnect()
            self.multi_conn.inactive[conn_header.port] = conn_header
            self.multi_conn.active.pop(conn_header.port)
