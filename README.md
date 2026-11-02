<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/_static/logos-dark/sfdctrust-logo-dark-320.png">
    <img src="docs/_static/logos/sfdctrust-logo-320.png" alt="sfdctrust logo" width="200">
  </picture>
</p>

# sfdctrust

An unofficial, community-maintained Python SDK project for the **Salesforce My Trust Center
API**. It is not affiliated with or supported by Salesforce.

> [!WARNING]
> The project is in development. API clients and resource operations are not implemented yet.

The API exposes only tenants authorized by the caller's personal access token (PAT);
empty results do not establish Salesforce-wide health.

See the [API contract and implementation decisions](docs/API_CONTRACT.md) for the verified
operation inventory, schema notes, authentication rules, and next implementation steps.

## Development

Requires Python **3.12 or later** and Poetry **2.2 or later, below 3**.
From this checkout:

```sh
poetry install
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry build
```

The runtime foundation uses HTTPX and Pydantic v2. Tests are offline and require no PAT.
Authentication configuration is still a proposed contract; no credential setup is needed
for this foundation. Do not place real tokens in source, examples, or test fixtures.

The documentation uses Sphinx with the optional `docs` dependency group:

```sh
poetry install --with docs
poetry run sphinx-build -W --keep-going -E -a -b html docs docs/_build/html
```

See [Maintain the documentation](docs/maintainers/documentation.md) for details.
