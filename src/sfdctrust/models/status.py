# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.models.status
:Synopsis:          Typed status snapshot models
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
"""

from __future__ import annotations

from pydantic import Field

from ._wire import _WireModel
from .events import EventSummary

__all__ = ['EventTypeBuckets', 'StatusSnapshot']


class EventTypeBuckets(_WireModel):
    """All four event categories, including empty arrays."""

    patch: list[EventSummary]
    incident: list[EventSummary]
    maintenance: list[EventSummary]
    informational_message: list[EventSummary] = Field(alias='informationalMessage')


class StatusSnapshot(_WireModel):
    """Ongoing and upcoming events visible to the client's authorized tenants."""

    ongoing: EventTypeBuckets
    upcoming: EventTypeBuckets
