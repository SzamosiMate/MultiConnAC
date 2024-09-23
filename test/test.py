from port import Port
from multi_conn_ac import MultiConn
from archicad_connection import ArchiCADConnection as ac
import asyncio

def connect_and_run_ac_command():
    conn = MultiConn()
    conn.connect.all()

    for conn_header in conn.open_port_headers.values():
        print(conn_header.ac.commands.GetAllElements())

def connect_and_run_core_command():
    conn = MultiConn()
    conn.connect.all()

    for conn_header in conn.open_port_headers.values():
        print(asyncio.run(conn_header.core.post_tapir_command('GetAddOnVersion')))

if __name__ == "__main__":
    connect_and_run_ac_command()
    connect_and_run_core_command()
    command = ac.commands.GetAllElements
