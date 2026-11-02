# Installation

These steps install `sfdctrust` from a source checkout for development.

## Prerequisites

- Python 3.12 or later
- [Poetry](https://python-poetry.org/docs/) 2.2 or later, below 3

## Install from source

```sh
git clone https://github.com/jeffshurtliff/sfdctrust.git
cd sfdctrust
poetry install
```

This creates a virtual environment with the package, its runtime dependencies and the
development tools. To also install the documentation tools, add the optional `docs` group:

```sh
poetry install --with docs
```

## Check the installation

```sh
poetry run python -c "import sfdctrust; print(sfdctrust.__version__)"
poetry run pytest -q
```

The tests are offline and do not need a personal access token (PAT).

```{caution}
Never place real PATs in source files, examples or test fixtures.
```
