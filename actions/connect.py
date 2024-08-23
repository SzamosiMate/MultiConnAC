from .actions import *


class Connect(Action):

    def execute_action(self, conn_headers: list[ConnHeader]) -> None:
        for conn_header in conn_headers:
            print(f'connecting {conn_header.ProductInfo}')
            if type(conn_header.ProductInfo) is ProductInfo:
                conn_header.connect()
                self.multi_conn.active[conn_header.port] = conn_header
                self.multi_conn.inactive.pop(conn_header.port)
