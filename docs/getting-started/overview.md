# Overview

`sfdctrust` is a Python SDK for the
[Salesforce My Trust Center API](https://developer.salesforce.com/docs/mytrust-api/overview.html).
It aims to make tenant status and event data easy to retrieve and integrate into
Python applications, scheduled monitoring, ITSM systems and AI agents.

```{important}
`sfdctrust` targets the My Trust Center API, not the legacy Salesforce Trust Status API.
It is unofficial and is not affiliated with or supported by Salesforce.
```

## Project status

The project is in development. The package currently exposes its version
(`sfdctrust.__version__`) and has a documented API contract, but the API client and
resource operations are not implemented yet. Pages for them will be added as they land.

## Scope and visibility

- The API returns data only for the tenants that the caller's personal access token (PAT)
  is authorized to see.
- My Trust Center does not cover every Salesforce product or service.
- A missing event, empty status bucket or absent tenant does not mean that Salesforce
  services are healthy.

See the {doc}`../API_CONTRACT` for the verified operations, schemas, authentication
rules and pagination behavior.

## Requirements

- Python 3.12 or later
- Runtime dependencies: [HTTPX](https://www.python-httpx.org/) and
  [Pydantic v2](https://docs.pydantic.dev/latest/)
