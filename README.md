<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/_static/logos-dark/sfdctrust-logo-dark-320.png">
    <img src="docs/_static/logos/sfdctrust-logo-320.png" alt="sfdctrust logo" width="200">
  </picture>
</p>

# sfdctrust

An unofficial, community-maintained Python SDK project for the **Salesforce My Trust Center
API**. It is not affiliated with or supported by Salesforce.

The project is in development. The synchronous client supports listing one page of tenants.

The API exposes only tenants authorized by the caller's personal access token (PAT);
empty results do not establish Salesforce-wide health.

See the [API contract and implementation decisions](docs/API_CONTRACT.md) for the verified
operation inventory, schema notes, authentication rules, and next implementation steps.

## Quickstart

Install from this checkout with `python -m pip install .` on Python 3.12 or later.
Set `SFDCTRUST_PAT` in the process environment using a PAT from My Trust Center.

```python
from sfdctrust import TrustCenterClient

with TrustCenterClient.from_env() as client:
    page = client.tenants.list()
    for tenant in page.tenants:
        print(tenant.id, tenant.name)
```

If `page.next_page_token is not None`, request the next page with
`client.tenants.list(page_token=page.next_page_token)` inside the same context.
If you supplied `page_size` or `locale` on the first call, repeat those values.
See the [quickstart](docs/getting-started/quickstart.md) and
[tenant reference](docs/reference/tenants.md) for details.

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

The SDK uses HTTPX and Pydantic v2. Tests run offline with synthetic PATs.

The [exception hierarchy](docs/reference/exceptions.rst) is available from `sfdctrust`, including
`ConfigurationError`, `AuthenticationError`, and the shared `TrustCenterError` base.
See [authentication](docs/reference/authentication.md) for the implemented boundaries.

The documentation uses Sphinx with the optional `docs` dependency group:

```sh
poetry install --with docs
poetry run sphinx-build -W --keep-going -E -a -b html docs docs/_build/html
```

See [Maintain the documentation](docs/maintainers/documentation.md) for details.
