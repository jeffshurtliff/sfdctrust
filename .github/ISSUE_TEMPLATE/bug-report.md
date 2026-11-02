---
name: Bug Report
about: Report a bug or unexpected behavior in sfdctrust
title: "[BUG] <short, descriptive summary>"
labels: bug
assignees: ''

---

## Bug Description

Provide a clear and concise description of the bug.  
What happened, and what did you expect to happen instead?

---

## Steps to Reproduce

Please provide **exact steps** so the issue can be reproduced reliably.

1. …
2. …
3. …

If applicable, include:
- Client and resource/method called (e.g. `client.tenants.list_all()`)
- My Trust Center API operation(s) involved, if known
- How the PAT was supplied (explicit argument or `SFDCTRUST_PAT`; never the value itself)

---

## Expected Behavior

Describe what you expected to happen.

---

## Actual Behavior

Describe what actually happened, including any error messages or unexpected results.

---

## Code Sample (if applicable)

Please include a **minimal, reproducible example**.

```python
# Example code that triggers the issue
```

⚠️ **Do not include secrets or real tenant data** (personal access tokens, `Authorization` headers, tenant IDs, real incident details, etc.). Use synthetic values.

---

## Environment Details

Please complete the following information:

- **sfdctrust version**:
- **Python version** (e.g. 3.12.7):
- **HTTPX and Pydantic versions** (`pip list | grep -iE 'httpx|pydantic'`):
- **Operating system**:
- **Installation method**:
  - [ ] pip
  - [ ] Poetry
  - [ ] Other (please specify)
- **Virtual environment**:
  - [ ] venv
  - [ ] virtualenv
  - [ ] Conda
  - [ ] Poetry
  - [ ] Other (please specify)
  - [ ] None

---

## Traceback / Logs

If applicable, include the **full traceback or relevant logs** below.

```text
Paste traceback or logs here
```

---

## Security Considerations

- [ ] I have verified this issue does **not** expose credentials or sensitive data
- [ ] This issue is **not** a security vulnerability (if it is, please do **not** file a public issue)

If this may be security-related, please report it responsibly instead of filing a public issue.

---

## Additional Context

Add any other context that may help diagnose the problem:
- Workarounds you’ve tried
- Related issues or PRs
- Tenant access scope of the PAT, at a high level (e.g. "one tenant", "several tenants")

---

## Acknowledgements

Thanks for taking the time to report this issue — detailed reports help make sfdctrust better for everyone.
