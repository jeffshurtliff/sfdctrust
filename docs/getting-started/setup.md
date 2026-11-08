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
| Built-in SQLite PAT store | Scripts and jobs running on one computer under the same operating-system account | The store saves the PAT between sessions and saves its replacement when you explicitly request refresh. |

An **environment variable** is a setting available to a running program.
A **PAT store** saves the PAT so your script can use it again later.
Option B uses the built-in `SQLitePATStore`. Integrations using other secret
storage systems can continue to supply their own adapter.

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

## Option B. Create a local SQLite PAT store

SQLite is a small database stored in a file. The package includes a command
that creates the store and **seeds** it, meaning it saves your first PAT.
Standard Python installations supply SQLite; no database server or extra
package is needed.

```{important}
Use a private folder on an encrypted local drive, outside OneDrive, iCloud
Drive, Dropbox, network shares, and source control. The database contains
the PAT in readable form while the drive is unlocked. The SDK checks file
protection but does not check drive encryption or detect every sync service.
All scripts that refresh the same PAT must use this same database, on this
computer, under the same operating-system account.
```

1. With your Python environment active, run this command **in your terminal**, paste the PAT at the hidden prompt,
   and press Enter.

   ```sh
   python -m sfdctrust.pat_store init
   ```

   You should see `Initialized the private SQLite PAT store.` The command
   creates `.sfdctrust/pat.sqlite3` under your home directory. It refuses to
   overwrite any existing database, including one with an unfinished refresh.
2. Run `python`. At the Python prompt, create
   a client using the store you just seeded.

   ```python
   from sfdctrust import SQLitePATStore, TrustCenterClient

   store = SQLitePATStore()
   client = TrustCenterClient.from_store(store)
   ```

   The client reads its credential from the store even if
   `SFDCTRUST_PAT` is set. Keep this session open and follow the read
   and refresh steps in {doc}`quickstart`. To use the saved PAT another
   day, repeat step 2. There is no downloaded adapter to keep alongside your script.

### Choose another location or name

For a second PAT lineage, choose an alias:

```sh
python -m sfdctrust.pat_store init --alias secondary
```

The `secondary` alias uses `~/.sfdctrust/secondary.sqlite3`.
Aliases accept letters, numbers, hyphens,
and underscores; Windows reserved names such as `CON` are rejected.
An alias selects a different store; it does not copy an existing PAT.

For a different encrypted local location, use a full database filename:

```sh
python -m sfdctrust.pat_store init --path "path/to/private-folder/pat.sqlite3"
```

The command can create the final private folder when its parent exists.
It checks existing folders instead of changing their permissions. Use either
`--path` or `--alias`.

For a job whose environment already contains the initial PAT, add `--from-env`
to read `SFDCTRUST_PAT`, or `--from-env=SFDCTRUST_PAT_ALT` to select another variable.
These options save that value once. They do not change the environment or
keep it updated after refresh. There is no command-line argument for the PAT itself.

### Opening an existing store

When opening an existing store in Python, use the same path or alias you
used during initialization. If you leveraged the default path and alias with 
`init` then you can open the store with `store = SQLitePATStore()` without needing 
to pass any parameters.

For stores created in a non-default directory or with a non-default alias, you will 
need to pass either the `path` or `alias` parameter when calling `SQLitePATStore()`.

Since `path` is the first argument, you can pass
it positionally as `store = SQLitePATStore('path/to/private-folder/pat.sqlite3')`
or explicitly as `store = SQLitePATStore(path='path/to/private-folder/pat.sqlite3')`.
Both forms open the same database. To open a store in the default `~/.sfdctrust/` directory 
by its alias, use `store = SQLitePATStore(alias='secondary')`.

### If initialization fails

Check that the destination is new, the containing folders exist, and the
store folder is private to your account. On Windows, use a local drive that
supports access-control lists, such as NTFS. An existing folder may need your
administrator's help to prepare; the SDK will not broaden access or silently
repair it. If a failed initialization left a file, inspect it before removing
it or choose a fresh alias. See {doc}`../reference/authentication` for the
exact protection requirements and the transition from the older downloadable example.
