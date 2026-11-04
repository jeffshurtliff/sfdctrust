Package
=======

.. py:module:: sfdctrust

The top-level ``sfdctrust`` package is the stable import location for the public
API. Underscore-prefixed modules are implementation details.

.. py:class:: TrustCenterClient(pat, *, http_client=None, max_retries=2)

   Configure a synchronous client with an explicit PAT. Construction makes no
   network requests.

   .. py:classmethod:: from_env(*, pat=..., http_client=None, max_retries=2)

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
the underlying transport, which may implement its own retries.
Both entry points accept ``max_retries: int = 2``, the number of additional
SDK attempts per eligible request. Integers from 0 through 5 are valid.
Booleans and other invalid values raise ``ConfigurationError``.
See :doc:`transport` for retry timing. See :doc:`tenants` and :doc:`events-and-status` for the resource operations.

.. autodata:: __version__
   :no-value:

   The installed package version as a string, such as ``1.0.0.dev0``.
