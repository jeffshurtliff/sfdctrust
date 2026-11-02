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

The documentation dependency group is optional. A Sphinx build is not configured yet.
