# Prepare to use sfdctrust

After {doc}`installation`, you need a personal access token (PAT) from
Salesforce My Trust Center. A PAT is a secret string that Salesforce uses
to identify your requests and decide which tenants you can see. Treat it
like a password. The client sends it for you when you make an API call.

## Get a PAT from My Trust Center

1. Sign in to [Salesforce My Trust Center](https://my.trust.salesforce.com/)
   with your Trailblazer account and verify that you can see the tenants
   you intend to query.
2. In **Settings**, find **Personal Access Tokens** and choose **Create
   Token**. Give it a recognizable name and choose a 7-, 15-, or 30-day
   lifetime.
3. Copy the token while it is visible. Salesforce displays it once. Enter
   it directly at the hidden prompt in one of the setup options below, or
   keep it in your organization's approved secret manager until you need it.
   Paste the token itself, without surrounding quotes or a `Bearer` prefix.

Salesforce allows one active PAT. If the account already has one, check
where it is used before revoking it. Use a dedicated test identity with
tenant access for the rotation walkthrough if other integrations depend
on your existing PAT. See the
[Salesforce authentication guide](https://developer.salesforce.com/docs/mytrust-api/authentication.html).

## Choose how to supply your PAT

| Option | Use it for | What happens to the PAT |
| --- | --- | --- |
| Environment variable | A quick read-only session or a job whose environment is managed by your organization | Python reads the value from `SFDCTRUST_PAT` when the client is created. To change it, supply a new value and create a new client. |
| PAT store | Testing refresh or integrating with persistent secret storage | The store saves the token between sessions. When you request refresh, the client can save the replacement before it switches tokens. |

An **environment variable** is a setting available to a running program.
A **PAT store** is where an application can read and safely replace a saved
PAT. The SDK works with a small Python object called an *adapter* that
handles the actual storage. Option B supplies a working adapter for a
single-machine test.

Keep the PAT out of source code, command arguments, chat, screenshots,
and logs. Both paths below use a prompt that hides what you type.

## Option A. Read using an environment variable

Open an interactive Python session by running `python` in your activated
environment. Type or paste the following into Python. Run the prompt on
its own, then paste the PAT and press Enter. The characters stay hidden.

```python
import os
import warnings
from getpass import GetPassWarning, getpass

warnings.filterwarnings('error', category=GetPassWarning)
os.environ['SFDCTRUST_PAT'] = getpass('My Trust Center PAT: ')
```

If Python cannot hide your input, use a terminal window in place of an IDE
output panel. Once the prompt completes, create the client in the same
Python session.

```python
from sfdctrust import TrustCenterClient

client = TrustCenterClient.from_env()
```

This example sets the variable only in the current Python process. Programs
started from that process can inherit the value. You can also launch Python
from a job that already supplies `SFDCTRUST_PAT` and start with the
client creation step. Use {doc}`quickstart` in the same session to verify
authentication and read data. When finished, close the client and exit Python
to end the temporary session.

## Option B. Create and seed a local test store

The example adapter uses SQLite, a small database stored on disk.
It comes with a setup command that creates the database and **seeds** it,
meaning it saves the first PAT. Python supplies SQLite on standard
installations, and the example needs no database server or extra packages.

```{important}
Use this example for a test on one computer. The database contains the PAT
in readable form when the volume is unlocked. Before entering a real PAT,
confirm your home directory is on an encrypted local volume and is private
to your account. Keep the store outside shared or synced folders and source
control. For a deployed integration, use an approved secret storage system
and an adapter that meets the {doc}`../reference/authentication` contract.
```

1. {download}`Download local_pat_store.py <_examples/local_pat_store.py>`.
   If reading from a checkout, copy `docs/getting-started/_examples/local_pat_store.py`
   to your working directory. In your terminal, change into the directory
   containing that file. Keep your Python environment active.
2. Run this command **in your terminal**, paste the PAT at the hidden prompt,
   and press Enter.

   ```sh
   python local_pat_store.py seed
   ```

   You should see `Saved the PAT in the local test store.` The example
   creates `.sfdctrust/pat.sqlite3` under your home directory.
   Seeding refuses to overwrite an existing PAT. If you need to use a
   different private, encrypted local location, pass
   `--directory "path/to/private-folder"` to the seed command and pass the
   same directory as a `pathlib.Path` to `LocalPATStore` below.
3. From the same directory, run `python`. At the Python prompt, create
   a client using the store you just seeded.

   ```python
   from local_pat_store import LocalPATStore
   from sfdctrust import TrustCenterClient

   store = LocalPATStore()
   client = TrustCenterClient.from_store(store)
   ```

   For a custom location, first run `from pathlib import Path`, then
   use `store = LocalPATStore(Path("path/to/private-folder"))` with the
   directory you supplied to the seed command.

   The client reads its credential from the store even if
   `SFDCTRUST_PAT` is set. Keep this session open and follow the read
   and refresh steps in {doc}`quickstart`. To use the saved PAT another
   day, repeat step 3.

If Python cannot import `local_pat_store`, check the downloaded filename
and the directory you launched Python from. If the seed command cannot
write the store, check that the directory exists or that its parent is
writable. On macOS and Linux the example requires the store directory and
database to be owned by you with no group or other access. On Windows,
check the folder's **Properties → Security** for access by other users.
