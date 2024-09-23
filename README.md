# MultiConnAC


![License](https://img.shields.io/github/license/SzamosiMate/MultiConnAC) ![Issues](https://img.shields.io/github/issues/SzamosiMate/MultiConnAC) ![Forks](https://img.shields.io/github/forks/SzamosiMate/MultiConnAC) ![Stars](https://img.shields.io/github/stars/SzamosiMate/MultiConnAC)

## About

MultiConnAC is a connection object for ArchiCAD’s JSON API and its Python wrapper, designed to manage multiple open instances of ArchiCAD simultaneously

## Features

- Connects to multiple or all open instances of ArchiCAD
- Utilizes ArchiCAD's official Python package
- Efficiently handles I/O-constrained operations with concurrent or asynchronous code

## Installation

1. Download all files, and install requirements.txt.
2. The package uses the [Tapir Archicad Add-On](https://github.com/ENZYME-APD/tapir-archicad-automation?tab=readme-ov-file). It is recommended to install this add-on to access all features. 

## Usage

Disclaimer:
The connection object is functional but still in the early stages of development. It is currently untested, and its interfaces may change in future updates.

Run command on all windows using the official python package
```python 
    conn = MultiConn()
    conn.connect.all()

    for conn_header in conn.open_port_headers.values():
        print(conn_header.ac.commands.GetAllElements())
```
Run command on all windows using basic helper functions
```python 
def connect_and_run_core_command():
    conn = MultiConn()
    conn.connect.all()

    for conn_header in conn.open_port_headers.values():
        print(asyncio.run(conn_header.core.post_tapir_command('GetAddOnVersion')))
```