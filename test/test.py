from port import Port
from multi_conn_ac import MultiConn
from archicad_connection import ArchiCADConnection as ac
import asyncio

def connect_and_run_ac_command():
    conn = MultiConn()
    conn.connect.all()

    for conn_header in conn.open_port_headers.values():
        print(conn_header.archicad.commands.GetAllElements())

def connect_and_run_core_command():
    conn = MultiConn()
    conn.connect.all()

    for conn_header in conn.open_port_headers.values():
        print(conn_header.core.post_tapir_command('GetAddOnVersion'))

def connect_and_run_all_ac_command():
    conn = MultiConn()
    conn.connect.all()

    elements = conn.archicad.commands.GetAllElements()
    bb3ds = conn.archicad.commands.Get3DBoundingBoxes(elements)
    print(bb3ds)


if __name__ == "__main__":
    connect_and_run_ac_command()
    connect_and_run_core_command()
    connect_and_run_all_ac_command()







