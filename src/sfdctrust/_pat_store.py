# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._pat_store
:Synopsis:          Versioned credential store contract for explicit PAT rotation
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     04 Nov 2026
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from typing import NoReturn, Protocol, runtime_checkable
from uuid import UUID

from pydantic import SecretStr

from ._auth import _validate_pat
from ._exceptions import ConfigurationError


@dataclass(frozen=True, slots=True, eq=False)
class PATStoreRecord:
    """A trusted adapter's snapshot of one PAT lineage.

    :param revision: Unique version of the credential, stable across pending marker changes.
    :param pat: The PAT without the Bearer prefix.
    :param pending_attempt: Unique identifier of the unresolved rotation, if any.
    """

    revision: UUID
    pat: InitVar[str]
    pending_attempt: UUID | None = None
    _secret: SecretStr = field(init=False, repr=False)

    def __post_init__(self, pat: str) -> None:
        if type(self.revision) is not UUID or (self.pending_attempt is not None and type(self.pending_attempt) is not UUID):
            raise ConfigurationError('PAT store revisions and attempt identifiers must be UUIDs.')
        _validate_pat(pat)
        object.__setattr__(self, '_secret', SecretStr(pat))

    def get_pat(self) -> str:
        """Return the secret for trusted store adapter I/O only."""
        return self._secret.get_secret_value()

    def __getstate__(self) -> NoReturn:
        raise TypeError('PAT store records cannot be serialized.')


@runtime_checkable
class PATStore(Protocol):
    """Durable, atomic store for one PAT lineage shared by all rotators.

    Implementations must provide strongly consistent reads and durable
    compare-and-swap across processes. A pending attempt survives loss of a
    process or lease and is cleared only by a coordinated state transition.
    """

    def load(self) -> PATStoreRecord | None:
        """Return the current record, or None for an unseeded lineage."""
        ...

    def compare_and_swap(self, *, expected_revision: UUID, expected_attempt: UUID | None, replacement: PATStoreRecord) -> bool:
        """Conditionally and durably replace the complete record.

        :param expected_revision: Credential version that must still be current.
        :param expected_attempt: Pending marker that must still match, including None.
        :param replacement: Full next record, with the credential and marker written atomically.
        :returns: True only after durable commit. False if the comparison failed
                  and no write occurred. Raise if the outcome cannot be confirmed.
        """
        ...
