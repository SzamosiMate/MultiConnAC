from .actions import *


class Connect(Action):

    def execute_action(self, conn_headers: list[ConnHeader]) -> None:
        for conn_header in conn_headers:
            print(f'connecting {conn_header.ProductInfo}')
            conn_header.connect()
