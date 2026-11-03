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

The project is in development. The synchronous client supports tenant listing, status snapshots,
event search, event details, and tenant details. See the {doc}`quickstart` and {doc}`exception hierarchy <../reference/exceptions>`.

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
