from .actions import *


class Disconnect(Action):

    def execute_action(self, conn_headers: list[ConnHeader]) -> None:
        for conn_header in conn_headers:
            conn_header.disconnect()
