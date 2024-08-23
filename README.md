# MultiConnAC


![License](https://img.shields.io/github/license/SzamosiMate/MultiConnAC) ![Issues](https://img.shields.io/github/issues/SzamosiMate/MultiConnAC) ![Forks](https://img.shields.io/github/forks/SzamosiMate/MultiConnAC) ![Stars](https://img.shields.io/github/stars/SzamosiMate/MultiConnAC)

## Table of Contents

- [About](#about)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)

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

The connection object is functional but still in the early stages of development. It is currently untested, and its interfaces may change in future updates.

```python 
conn = MultiConn()
conn.Connect.all()
conn.Run_Async.all('CommandName', 'parameters')
```
