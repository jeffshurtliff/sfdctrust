Package
=======

.. py:module:: sfdctrust

The top-level ``sfdctrust`` package is the stable import location for the public
API. Underscore-prefixed modules are implementation details.

.. py:class:: SQLitePATStore(path=None, *, alias=None)

   Open an existing, protected SQLite store for one PAT lineage on this host.
   ``path`` accepts a string or ``pathlib.Path``. ``alias`` selects another
   basename in ``~/.sfdctrust`` and is mutually exclusive with ``path``.
   Connections close after each operation; the adapter needs no close method.

   .. py:classmethod:: initialize(*, pat, path=None, alias=None)

      Exclusively create a private database, durably save the initial PAT, and
      return the adapter. Every existing destination is refused. The final
      private directory may be created if its parent exists. No existing
      permissions are changed. Invalid input or initialization failure raises
      ``ConfigurationError``. Prefer the hidden-prompt module command for
      interactive setup.

   .. py:method:: load()

      Return the latest committed ``PATStoreRecord`` (including its pending
      marker), or ``None`` if the supported database is unseeded. Unsafe access,
      incompatible schema, and invalid records raise ``ConfigurationError``.

   .. py:method:: compare_and_swap(*, expected_revision, expected_attempt, replacement)

      Compare both UUID identifiers, including a ``None`` attempt, and commit
      the complete replacement record atomically. Return ``True`` only after
      durable commit and ``False`` only for a comparison mismatch. Invalid
      arguments or an unconfirmed write raise ``PATPersistenceError``.

   See :ref:`sqlite-pat-store` for supported storage, protection, initialization,
   schema compatibility, and recovery.

.. py:class:: TrustCenterClient(pat, *, http_client=None, max_retries=2)

   Configure a synchronous client with an explicit PAT. Construction makes no
   network requests.

   .. py:classmethod:: from_env(*, pat=..., http_client=None, max_retries=2)

      Read ``SFDCTRUST_PAT`` if ``pat`` is omitted. An explicit override is
      validated directly, including an explicit ``None``, which raises
      ``ConfigurationError``. See :doc:`authentication`.

   .. py:classmethod:: from_store(store, *, http_client=None, max_retries=2)

      Load a caller-supplied PAT store. See :doc:`authentication` for the
      adapter contract, operator recovery and public result types.

   .. py:method:: refresh_pat(*, expires_in_days=None)

      Rotate a store-backed PAT once and return a secret-free
      ``PATRefreshResult`` after durable storage.

   .. py:method:: retry_pat_persistence()

      Reconcile or retry storing a replacement held by this client. Returns
      ``PATRefreshResult`` after confirming durable storage.

   .. py:method:: close()

      Close SDK-owned HTTP connections.

Use the client as a synchronous context manager to close SDK-owned connections.
All credential entry points accept a trusted, caller-owned HTTPX client through
``http_client=``. Context exit and ``close()`` leave an injected client open. The
SDK still applies its fixed destination, per-attempt timeouts, redirect policy,
and error translation. The injected client controls TLS, proxies, hooks, and
the underlying transport, which may implement its own retries.
All entry points accept ``max_retries: int = 2``, the number of additional
SDK attempts per eligible request. Integers from 0 through 5 are valid.
Booleans and other invalid values raise ``ConfigurationError``.
See :doc:`transport` for retry timing. See :doc:`tenants` and :doc:`events-and-status` for the resource operations.

Async client
------------

Import ``AsyncTrustCenterClient`` from ``sfdctrust`` for use with asyncio.
Construction and ``from_env()`` are ordinary calls. Use ``async with``
or ``await client.aclose()`` to close SDK-owned HTTP connections.
All async credential entry points accept an optional trusted, caller-owned
``httpx.AsyncClient``. Use the client and its adapter on one event loop.

Await ``tenants.list()``, ``tenants.get()``, ``status.snapshot()``,
``events.search()``, ``events.get()``, ``tenants.list_all()``, and
``events.search_all()``. They use the same arguments and models as the
synchronous operations. Consume ``tenants.iter_all()`` and
``events.iter_search()`` directly with ``async for``. These two methods
return lazy async iterators when called. Collectors begin traversal when
their coroutines run.

.. py:class:: AsyncTrustCenterClient(pat, *, http_client=None, max_retries=2)

   Configure an asyncio client with an explicit PAT.

   .. py:classmethod:: from_env(*, pat=..., http_client=None, max_retries=2)

      Use the explicit PAT override if supplied. Otherwise read ``SFDCTRUST_PAT``.

   .. py:method:: from_store(store, *, http_client=None, max_retries=2)
      :classmethod:
      :async:

      Load a seeded ``AsyncPATStore`` and check for a pending attempt.

   .. py:method:: refresh_pat(*, expires_in_days=None)
      :async:

      Rotate the PAT once and return ``PATRefreshResult`` after durable storage.

   .. py:method:: retry_pat_persistence()
      :async:

      Reconcile storage of a replacement held by this client.

   .. py:method:: aclose()
      :async:

      Close SDK-owned HTTP connections.

.. py:class:: AsyncPATStore

   Protocol for durable asynchronous storage shared by every rotator of one
   PAT lineage. See :doc:`authentication` for the adapter contract and recovery.

   .. py:method:: load()
      :async:

      Return the latest committed ``PATStoreRecord`` or ``None`` for an unseeded store.

   .. py:method:: compare_and_swap(*, expected_revision, expected_attempt, replacement)
      :async:

      Compare the revision and pending attempt and durably replace the entire record.

.. autodata:: __version__
   :no-value:

   The installed package version as a string.
