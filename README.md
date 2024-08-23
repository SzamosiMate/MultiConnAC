# MultiConnAC


![License](https://img.shields.io/github/license/SzamosiMate/MultiConnAC) ![Issues](https://img.shields.io/github/issues/SzamosiMate/MultiConnAC) ![Forks](https://img.shields.io/github/forks/SzamosiMate/MultiConnAC) ![Stars](https://img.shields.io/github/stars/SzamosiMate/MultiConnAC)

## Table of Contents

- [About](#about)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)
- [Acknowledgements](#acknowledgements)

## About

MultiConnAC is a connection object for ArchiCAD’s JSON API and its Python wrapper, designed to manage multiple open instances of ArchiCAD simultaneously

## Features

- Connects to multiple or all open instances of ArchiCAD
- Utilizes ArchiCAD's official Python package
- Efficiently handles I/O-constrained operations with concurrent or asynchronous code

## Installation

TODO

## Usage

```python 
conn = MultiConn()
conn.Connect.all()
conn.Run_Async.all('CommandName', 'parameters')
```
## Contributing

Contributions are what make the open-source community such an amazing place to be, learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Contact

Your Name - [@your-twitter-handle](https://twitter.com/your-twitter-handle) - email@example.com

Project Link: [https://github.com/your-username/your-repo](https://github.com/your-username/your-repo)

## Acknowledgements

- **[LibraryName](https://github.com/username/libraryname)** - This project was built using [LibraryName], an open-source library for X, Y, and Z. We are grateful to the maintainers and contributors of [LibraryName] for their efforts in creating such a valuable resource.
