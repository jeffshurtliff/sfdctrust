# Qualify one deliberate PAT rotation

This is the credential-changing phase of
[issue #8](https://github.com/jeffshurtliff/sfdctrust/issues/8). Run it in a
separate session with explicit authorization for a dedicated non-production
PAT lineage. Quiesce other jobs using that lineage and make sure you can
recover through My Trust Center. A successful refresh immediately revokes
the original PAT. See [Salesforce's authentication guide](https://developer.salesforce.com/docs/mytrust-api/authentication.html)
and the SDK's {ref}`qualification-rotation-recovery` instructions below.

Use the verified wheel environment from {doc}`installed-wheel-qualification`.
Choose an unused database path on a private encrypted local volume, outside
sync and network folders, under trusted containing directories. The example
uses the user's home volume. The SQLite store enforces its file permissions
and refuses to seed an existing database. SQLite stores the PAT in plaintext
within the protected volume. See the {ref}`sqlite-pat-store` requirements.

## Seed, check the baseline, and rotate once

Run this command in a private interactive terminal. Supply the original test
PAT only at the hidden prompt. After confirming the baseline passes, type
`ROTATE` when prompted to send the one refresh request. Keep the process open
until you know whether the replacement was persisted.

```sh
qual_store="$HOME/.sfdctrust/issue-8-qualification.sqlite3"
"$qual_py" -I -i -c '
import logging
import sys
import warnings
from getpass import GetPassWarning, getpass

from sfdctrust import (
    APIStatusError,
    AuthenticationError,
    PATPersistenceError,
    PATRefreshAmbiguousError,
    SQLitePATStore,
    TrustCenterClient,
)

logging.disable(logging.CRITICAL)
client = None
old_pat = None
refreshed = False

try:
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        old_pat = getpass("Original test PAT (input is hidden): ")
    store = SQLitePATStore.initialize(pat=old_pat, path=sys.argv[1])
    client = TrustCenterClient.from_store(store, max_retries=0)
    print("PASS baseline tenant read, records =", len(client.tenants.list(page_size=1).tenants))
except (Exception, KeyboardInterrupt):
    print("FAIL baseline or store setup; stop and review before proceeding.")
else:
    try:
        approved = input("Type ROTATE to refresh this dedicated test lineage once: ") == "ROTATE"
    except (EOFError, KeyboardInterrupt):
        approved = False
    if not approved:
        print("SKIP refresh; operator did not confirm.")
    else:
        try:
            result = client.refresh_pat(expires_in_days=7)
        except PATPersistenceError:
            print("FAIL persistence confirmation; keep this process and client alive for recovery.")
        except PATRefreshAmbiguousError:
            print("FAIL ambiguous refresh; stop and follow the recovery runbook.")
        except APIStatusError as error:
            print("FAIL refresh, HTTP", error.status_code)
        except (Exception, KeyboardInterrupt):
            print("FAIL refresh; stop and follow the recovery runbook.")
        else:
            refreshed = True
            print("PASS refresh and replacement persistence")
            print("PASS refresh metadata" if result.metadata_valid else "FAIL refresh metadata schema")
            try:
                print("PASS replacement tenant read, records =", len(client.tenants.list(page_size=1).tenants))
            except (Exception, KeyboardInterrupt):
                print("FAIL replacement tenant read")
            try:
                with TrustCenterClient(pat=old_pat, max_retries=0) as original:
                    original.tenants.list(page_size=1)
            except AuthenticationError:
                print("PASS original PAT rejected, HTTP 401")
            except (Exception, KeyboardInterrupt):
                print("FAIL original PAT rejection check inconclusive")
            else:
                print("FAIL original PAT still accepted")

old_pat = None
if refreshed:
    try:
        client.close()
    except (Exception, KeyboardInterrupt):
        print("FAIL client close")
    print("Exit this interpreter and run the fresh-process check.")
' "$qual_store"
```

The original-PAT check uses a separate static client and one tenant-list
request with retries disabled. Only HTTP 401 counts as rejection. A successful
refresh with a metadata mismatch can still persist a valid replacement.
Record the metadata discrepancy and the read results separately.

(qualification-rotation-recovery)=
## Stop and recover on refresh failure

Use the {doc}`SDK recovery runbook <../reference/authentication>` under
**Recovery runbook** to distinguish rejection, ambiguous refresh, and
persistence failures. Keep any pending marker intact while resolving an
ambiguous result. The SDK may already have sent one harmless old-PAT probe.
Record the failed or inconclusive phase and stop this qualification attempt.
Keep the original client alive if the replacement write was unconfirmed.

For an unconfirmed **replacement** write, restore store access and paste this
block at the still-running Python prompt. It reconciles persistence
with store I/O alone. If it fails, retain the process and follow the recovery
runbook. Do not re-run the refresh command to recover.

```python
exec(
    """try:
    client.retry_pat_persistence()
except (Exception, KeyboardInterrupt):
    print("FAIL persistence recovery; keep the original client alive.")
else:
    print("PASS replacement persistence recovery")"""
)
```

## Verify from a fresh process

After a confirmed refresh, exit the first interpreter with `exit()`. Start a
new process using the same wheel and database path. It loads its credential
from the store and makes one read.

```sh
"$qual_py" -I -c '
import logging
import sys

from sfdctrust import SQLitePATStore, TrustCenterClient

logging.disable(logging.CRITICAL)
try:
    with TrustCenterClient.from_store(SQLitePATStore(sys.argv[1]), max_retries=0) as client:
        count = len(client.tenants.list(page_size=1).tenants)
except (Exception, KeyboardInterrupt):
    raise SystemExit("FAIL fresh-process tenant read") from None
print("PASS fresh-process tenant read, records =", count)
' "$qual_store"
```

Record only pass, fail, or skip and the sanitized reasons or counts. A
qualifying result includes the baseline, one successful refresh with a
persisted replacement, HTTP 401 for the original, and successful reads using
the replacement in both processes. Use the artifact identifiers recorded
during wheel verification. Keep the store protected while the test lineage
remains active and use the approved credential retirement process afterward.
