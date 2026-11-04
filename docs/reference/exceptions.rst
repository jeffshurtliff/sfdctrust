Exceptions
==========

Import these types from ``sfdctrust``. All SDK failures share
:class:`~sfdctrust.TrustCenterError`. A timeout is also a network failure;
authentication, rate-limit and not-found errors are also API status failures.
Malformed successful responses have their own branch.

.. code-block:: text

   TrustCenterError
   ├── ConfigurationError
   ├── NetworkError
   │   └── RequestTimeoutError
   ├── APIStatusError
   │   ├── AuthenticationError   (401)
   │   ├── RateLimitError        (429)
   │   └── NotFoundError         (404)
   ├── MalformedResponseError
   ├── PaginationError
   ├── PATRefreshPendingError
   ├── PATRefreshAmbiguousError
   └── PATPersistenceError

``APIStatusError(status_code)`` accepts integer statuses from 400 through 599.
Its specialized subclasses take no arguments and set their fixed status.
These errors retain only ``status_code`` and a static message containing that
status. They do not accept server messages, raw requests, responses or headers.
Request-ID capture is deferred until a documented safe source is verified.

The other branches accept ordinary exception arguments for SDK-authored,
secret-free messages. Never pass server content, credential values, HTTPX
requests or raw exception text to them. The existing base exception's
construction behavior is preserved.

A 401 does not distinguish invalid, missing, revoked or expired credentials.
A 404 does not distinguish nonexistent from unauthorized resources. A 429
does not imply a JSON body or a ``Retry-After`` header. The exceptions perform
no I/O, retries or credential refresh. The private transport translates HTTP
statuses before reading the response body and uses the base
:class:`~sfdctrust.TrustCenterError` for unexpected statuses such as redirects.

A traversal raises ``PaginationError`` if a further page would reuse a cursor
or exceed ``max_pages``. A lazy iterator may have already yielded items.
A server rejection of a cursor with HTTP 400 raises ``APIStatusError``.

.. autoclass:: sfdctrust.TrustCenterError
.. autoclass:: sfdctrust.ConfigurationError
.. autoclass:: sfdctrust.NetworkError
.. autoclass:: sfdctrust.RequestTimeoutError
.. autoclass:: sfdctrust.APIStatusError
.. autoclass:: sfdctrust.AuthenticationError
.. autoclass:: sfdctrust.RateLimitError
.. autoclass:: sfdctrust.NotFoundError
.. autoclass:: sfdctrust.MalformedResponseError
.. autoclass:: sfdctrust.PaginationError

See :doc:`authentication` for refresh outcomes and the recovery procedure.

.. autoclass:: sfdctrust.PATRefreshPendingError
.. autoclass:: sfdctrust.PATProbeResult
.. autoclass:: sfdctrust.PATRefreshAmbiguousError
.. autoclass:: sfdctrust.PATPersistenceError
