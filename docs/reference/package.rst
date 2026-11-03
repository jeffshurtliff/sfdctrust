Package
=======

.. py:module:: sfdctrust

The top-level ``sfdctrust`` package is the stable import location for the public
API. Underscore-prefixed modules are implementation details.

.. py:class:: TrustCenterClient(pat, *, http_client=None)

   Configure a synchronous client with an explicit PAT. Construction makes no
   network requests.

   .. py:classmethod:: from_env(*, pat=..., http_client=None)

      Read ``SFDCTRUST_PAT`` if ``pat`` is omitted. An explicit override is
      validated directly, including an explicit ``None``, which raises
      ``ConfigurationError``. See :doc:`authentication`.

   .. py:method:: close()

      Close SDK-owned HTTP connections.

Use the client as a synchronous context manager to close SDK-owned connections.
Both credential entry points accept a trusted, caller-owned HTTPX client through
``http_client=``. Context exit and ``close()`` leave an injected client open. The
SDK still applies its fixed destination, per-attempt timeouts, redirect policy,
and error translation. The injected client controls TLS, proxies, hooks, and
the underlying transport. See :doc:`tenants` for the resource operation.

.. autodata:: __version__
   :no-value:

   The installed package version as a string, such as ``1.0.0.dev0``.
