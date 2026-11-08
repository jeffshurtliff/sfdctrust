# Qualify the SQLite PAT store

The v0.2.0 store is synchronous and uses one private database on an encrypted
local volume, one host, and one OS account. It reuses the existing refresh protocol.
The tests use synthetic PATs and mock HTTP transports; no Salesforce
credentials are needed.

## Validation

The `SDK validation` GitHub Actions workflow tests macOS, Windows, and Ubuntu
with Python 3.12 and Ubuntu with Python 3.15. It includes native ACL tests,
spawned-process competition, abrupt exits, and an installed-wheel walkthrough.
The separate quality job checks Ruff, Bandit, distribution metadata, and
strict Sphinx output. Windows tests use native Windows APIs and an ordinary
hosted runner; no additional device or architecture matrix is required.

After installing a built wheel, run `python tests/package_smoke.py` from
the checkout to verify its module command, tenant and event reads, explicit
refresh, and reopening. The script rejects editable/source imports.

Record actual platform results before declaring the feature release-ready.
Local macOS success does not establish Windows or Linux qualification.
Do not use a live PAT as part of these checks. Any optional real-account
walkthrough requires separate maintainer authorization.

### Initial implementation results — 2026-11-06

| Environment/check | Observed result |
| --- | --- |
| Local macOS, Python 3.12 | 597 offline tests passed; 14 Windows-only cases skipped. Includes real macOS ACL checks and spawned-process/crash tests. |
| Fresh macOS Python 3.14 environment | Wheel installed offline with locked runtime dependencies; dependency consistency and the installed-package SQLite walkthrough passed. |
| Local quality/package checks | Ruff lint and formatting, Bandit, strict Poetry/lock checks, wheel/sdist builds, archive content checks, and strict Twine metadata validation passed. |
| Documentation | Strict Sphinx HTML build passed; setup, refresh, and recovery pages reviewed in the browser. |
| Hosted Windows and Ubuntu | Pending a maintainer or separately authorized push and the resulting GitHub Actions runs. No hosted success is claimed here. |

## Follow-up work

These items are outside this implementation. Keep this list as input to
follow-up GitHub issues after reviewing the completed feature:

- Built-in asynchronous SQLite adapter and cancellation qualification.
- Optional credential encryption/keychain integration in addition to ACLs
  and encrypted-volume requirements.
- An explicit, validated migration command for old example databases.
- Multi-host storage/coordination and automatic refresh scheduling, each
  with its own credential-lifecycle design.
- Broader filesystem/provider checks, complex corporate ACL support,
  advanced crash/power-loss fault injection, and additional platform or
  architecture qualification if demonstrated user needs justify them.

The current store does not claim automated encryption verification,
comprehensive network/sync-folder detection, or secure erasure of backups
and filesystem snapshots. These boundaries are documented in the
{doc}`../reference/authentication` reference.
