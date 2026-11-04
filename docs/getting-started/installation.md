# Installation

You need Python 3.12 or later and `pip`. The package is available on PyPI.

## Create a virtual environment

A virtual environment keeps the package and its dependencies separate from
your other Python projects. Open a terminal in the directory where you want
to save your example files.

**macOS or Linux**

```sh
python3 --version
python3 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell**

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If the version command reports an older version, install Python 3.12 or
later and use that interpreter to create the environment. If PowerShell
blocks activation, use the full path to your environment's Python, such as
`& "C:\path\to\sfdctrust\.venv\Scripts\python.exe"`, in place of `python`
in the remaining commands. When you open a new terminal, activate the same
environment again or use the full interpreter path.

## Install and verify

Install from PyPI:

```sh
python -m pip install sfdctrust
```

For a wheel, run `python -m pip install "path/to/file.whl"`, substituting
the path to the wheel you received. By default, `pip` downloads the
dependencies from the configured Python package index.

Confirm Python can import the installed package:

```sh
python -c "import sfdctrust; print(sfdctrust.__version__)"
```

If you see a version number, continue to {doc}`setup`. If Python reports
`ModuleNotFoundError`, check that you ran the install and import commands
using the same virtual environment.

## For contributors

To get a source checkout, run `git clone https://github.com/jeffshurtliff/sfdctrust.git`
and then `cd sfdctrust`. To install the package directly from this checkout,
run `python -m pip install .`.

To install development and test tools from the source checkout, use
[Poetry](https://python-poetry.org/docs/) 2.2 or later, below 3.

```sh
poetry install
poetry run pytest -q
```

The tests use synthetic tokens and run offline. To build the Sphinx
documentation, see {doc}`../maintainers/documentation`.
