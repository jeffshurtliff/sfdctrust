# Overview

`sfdctrust` is a Python package for reading Salesforce tenant status and events
from the [My Trust Center API](https://developer.salesforce.com/docs/mytrust-api/overview.html).
The API lets programs retrieve the same kinds of information you see in My
Trust Center, such as incidents or planned maintenance. The package takes care
of sending your requests and gives you Python objects with fields you can
use in scripts or applications.

```{important}
`sfdctrust` targets the My Trust Center API, not the legacy Salesforce Trust Status API.
It is unofficial and is not affiliated with or supported by Salesforce.
```

## What you can do

You can list tenants, read current and upcoming
events, search event history, and retrieve individual event timelines. You can
also explicitly refresh a personal access token when using a compatible store.
Begin with {doc}`installation`, then use {doc}`setup` to connect to My Trust Center.

## Scope and visibility

- The API returns data only for the tenants that the caller's personal access token (PAT)
  is authorized to see.
- My Trust Center does not cover every Salesforce product or service.
- A missing event, empty status bucket or absent tenant does not mean that Salesforce
  services are healthy.

See the {doc}`../API_CONTRACT` for the verified operations, schemas, authentication
rules and pagination behavior.

## Requirements

- Python 3.12 or later.
- A My Trust Center account with access to the tenants you want to query.
- Network access to the Salesforce API when running live examples.
