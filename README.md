# datasette-app-support

[![PyPI](https://img.shields.io/pypi/v/datasette-app-support.svg)](https://pypi.org/project/datasette-app-support/)
[![Changelog](https://img.shields.io/github/v/release/simonw/datasette-app-support?include_prereleases&label=changelog)](https://github.com/simonw/datasette-app-support/releases)
[![Tests](https://github.com/simonw/datasette-app-support/workflows/Test/badge.svg)](https://github.com/simonw/datasette-app-support/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/datasette-app-support/blob/main/LICENSE)

Part of https://github.com/simonw/datasette-app

## Installation

Install this plugin in the same environment as Datasette.

    $ datasette install datasette-app-support

## API endpoints

This plugin exposes APIs that are called by the Electron wrapper.

### /-/open-database-file

```
POST /-/open-database-file
{"path": "/path/to/file.db"}
```
Attaches a new database file to the running Datasette instance - used by the "Open Database..." menu option.

Returns HTTP 200 if it works, 400 with an `"error"` JSON string message if it fails.

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:

    cd datasette-app-support
    python3 -mvenv venv
    source venv/bin/activate

Or if you are using `pipenv`:

    pipenv shell

Now install the dependencies and test dependencies:

    pip install -e '.[test]'

To run the tests:

    pytest
