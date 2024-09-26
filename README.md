# MultiConnAC


![License](https://img.shields.io/github/license/SzamosiMate/MultiConnAC) ![Issues](https://img.shields.io/github/issues/SzamosiMate/MultiConnAC) ![Forks](https://img.shields.io/github/forks/SzamosiMate/MultiConnAC) ![Stars](https://img.shields.io/github/stars/SzamosiMate/MultiConnAC)

## About

MultiConnAC is a connection object for ArchiCAD’s JSON API and its Python wrapper, designed to manage multiple open instances of ArchiCAD simultaneously.

## Features

- Connects to multiple or all open instances of ArchiCAD
- Utilizes ArchiCAD's official Python package
- Can be used to run commands of the Tapir Archicad Add-On
- Efficiently handles I/O-constrained operations with concurrent or asynchronous code (currently only for establishing connection)

## Installation

1. Download all files, and install requirements.txt.
2. The package uses the [Tapir Archicad Add-On](https://github.com/ENZYME-APD/tapir-archicad-automation?tab=readme-ov-file). It is recommended to install this add-on to access all features. 

## Usage

Disclaimer:
The connection object is functional but still in the early stages of development. It is currently untested, and its interfaces may change in future updates.

To run a command on all active connections you can call a command directly on the MultiConn object. It will call the same method on all active ConnHeaders of the parent, with the provided attribute path.
The command will return a dictionary, where the keys are the ports of the ArchiCAD windows, and the values are the results of the command calls. 
If you use dictionaries with Port type keys as parameters, the call will match them to the correct ArchiCAD instance.

Run command on all windows using the official python package

```python 
def connect_and_run_all_ac_command():
    conn = MultiConn()
    conn.connect.all()

    elements = conn.archicad.commands.GetAllElements()
    bb3ds = conn.archicad.commands.Get3DBoundingBoxes(elements)
    print(bb3ds)
```

If you want more control, you can manually loop through all active connections, and call the commands directly.
Run command on all windows using basic helper functions
```python 
def connect_and_run_core_command():
    conn = MultiConn()
    conn.connect.all()

    for conn_header in conn.active.values():
        print(conn_header.core.post_tapir_command('GetAddOnVersion'))
```
