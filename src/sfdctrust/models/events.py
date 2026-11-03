# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.models.events
:Synopsis:          Typed event search, detail, and timeline models
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import Discriminator, Field, InstanceOf, Tag, ValidationInfo, field_validator, model_validator

from ._wire import _reject_null, _Timestamp, _WireModel

__all__ = [
    'EventType',
    'EventSearchScope',
    'EventSearchResponse',
    'EventSearchResult',
    'EventDetail',
    'EventSummary',
    'SubEventScope',
    'PatchEventData',
    'IncidentEventData',
    'MaintenanceEventData',
    'InformationalMessageEventData',
    'TimelineItem',
    'PatchTimelineItem',
    'IncidentTimelineItem',
    'MaintenanceTimelineItem',
    'InformationalMessageTimelineItem',
    'PatchNote',
]

EventType = Literal['patch', 'incident', 'maintenance', 'informationalMessage']


class EventSearchScope(_WireModel, extra='forbid', frozen=True):
    """One tenant to search, identified by its opaque, case-sensitive ID."""

    id: str = Field(min_length=1)
    type: Literal['tenant'] = 'tenant'


class SubEventScope(_WireModel):
    """Tenant membership keyed by opaque tenant IDs."""

    tenants: dict[str, dict[str, Any]]


class PatchEventData(_WireModel):
    release_id: str = Field(alias='releaseId')
    release_name: str = Field(alias='releaseName')
    release_version: str = Field(alias='releaseVersion')
    planned_start_time: _Timestamp | None = Field(alias='plannedStartTime')
    planned_end_time: _Timestamp | None = Field(alias='plannedEndTime')


class IncidentEventData(_WireModel):
    additional_information: str | None = Field(alias='additionalInformation')
    rca_link: str | None = Field(alias='rcaLink')
    rca_created_at: _Timestamp | None = Field(alias='rcaCreatedAt')


class MaintenanceEventData(_WireModel):
    planned_start_time: _Timestamp | None = Field(alias='plannedStartTime')
    planned_end_time: _Timestamp | None = Field(alias='plannedEndTime')
    additional_information: str | None = Field(alias='additionalInformation')


class InformationalMessageEventData(_WireModel):
    informational_message_type: str | None = Field(alias='informationalMessageType')


_EVENT_DATA = {
    'patch': PatchEventData,
    'incident': IncidentEventData,
    'maintenance': MaintenanceEventData,
    'informationalMessage': InformationalMessageEventData,
}


class _TimelineEntry(_WireModel):
    sub_event_id: str = Field(alias='subEventId')
    sub_event_type: str = Field(alias='subEventType')
    scope: SubEventScope
    created_at: _Timestamp = Field(alias='createdAt')
    message: str | None = None
    updated_at: _Timestamp | None = Field(default=None, alias='updatedAt')


class PatchNote(_WireModel):
    related_item: str | None = Field(default=None, alias='relatedItem')
    description: str | None = None

    _nonnull = field_validator('related_item', 'description', mode='before')(_reject_null)


class PatchTimelineItem(_TimelineEntry):
    publication_date: _Timestamp | None = Field(default=None, alias='publicationDate')
    planned_start_time: _Timestamp | None = Field(default=None, alias='plannedStartTime')
    planned_end_time: _Timestamp | None = Field(default=None, alias='plannedEndTime')
    contents: list[PatchNote] | None = None

    _nonnull = field_validator('contents', mode='before')(_reject_null)


class IncidentTimelineItem(_TimelineEntry):
    pass


class MaintenanceTimelineItem(_TimelineEntry):
    planned_start_time: _Timestamp | None = Field(default=None, alias='plannedStartTime')
    planned_end_time: _Timestamp | None = Field(default=None, alias='plannedEndTime')


class InformationalMessageTimelineItem(_TimelineEntry):
    pass


_TIMELINE_TYPES = {
    'patch_release_scheduled': 'patch',
    'patch_release_started': 'patch',
    'patch_release_ended': 'patch',
    'patch_release_notes': 'patch',
    'incident_started': 'incident',
    'incident_update': 'incident',
    'incident_resolved': 'incident',
    'maintenance_scheduled': 'maintenance',
    'maintenance_update': 'maintenance',
    'maintenance_started': 'maintenance',
    'maintenance_completed': 'maintenance',
    'maintenance_canceled': 'maintenance',
    'im_created': 'informationalMessage',
    'im_update_added': 'informationalMessage',
}


def _timeline_tag(value: object) -> str:
    subtype = value.get('subEventType') if isinstance(value, dict) else getattr(value, 'sub_event_type', None)
    return _TIMELINE_TYPES.get(subtype, 'unknown') if isinstance(subtype, str) else 'unknown'


TimelineItem = Annotated[
    Annotated[PatchTimelineItem, Tag('patch')]
    | Annotated[IncidentTimelineItem, Tag('incident')]
    | Annotated[MaintenanceTimelineItem, Tag('maintenance')]
    | Annotated[InformationalMessageTimelineItem, Tag('informationalMessage')]
    | Annotated[_TimelineEntry, Tag('unknown')],
    Discriminator(_timeline_tag),
]


class _Event(_WireModel):
    event_id: str = Field(alias='eventId')
    event_type: str = Field(alias='eventType')
    status: str
    products: list[str]
    services: list[str]
    created_at: _Timestamp = Field(alias='createdAt')
    title: str | None = None
    description: str | None = None
    start_time: _Timestamp | None = Field(default=None, alias='startTime')
    end_time: _Timestamp | None = Field(default=None, alias='endTime')
    duration: str | None = None
    display_duration: str | None = Field(default=None, alias='displayDuration')
    data: (
        InstanceOf[PatchEventData]
        | InstanceOf[IncidentEventData]
        | InstanceOf[MaintenanceEventData]
        | InstanceOf[InformationalMessageEventData]
        | dict[str, Any]
        | None
    ) = None

    @field_validator('data', mode='before')
    @classmethod
    def _parse_data(cls, value: object, info: ValidationInfo) -> object:
        _reject_null(value)
        model = _EVENT_DATA.get(info.data.get('event_type'))
        return model.model_validate(value) if model is not None else value


class EventSummary(_Event):
    """A scoped event in a status snapshot or tenant history."""

    scope: SubEventScope

    @model_validator(mode='after')
    def _exclude_timeline(self) -> Self:
        if self.model_extra and 'timeline' in self.model_extra:
            raise ValueError('Event summaries do not include a timeline.')
        return self


class EventSearchResult(EventSummary):
    """A scoped search result with lifecycle values for the matched tenant."""


class EventDetail(_Event):
    """An event and its optional tenant-scoped timeline."""

    timeline: list[TimelineItem] | None = None

    _nonnull = field_validator('timeline', mode='before')(_reject_null)

    @model_validator(mode='after')
    def _check_detail_shape(self) -> Self:
        if self.model_extra and 'scope' in self.model_extra:
            raise ValueError('Event detail does not include a top-level scope.')
        if self.event_type in _EVENT_DATA:
            for entry in self.timeline or ():
                category = _TIMELINE_TYPES.get(entry.sub_event_type)
                if category is not None and category != self.event_type:
                    raise ValueError('Timeline type does not match the parent event type.')
        return self


class EventSearchResponse(_WireModel):
    """One page of search results and its optional continuation token."""

    events: list[EventSearchResult] = Field(max_length=200)
    next_page_token: str | None = Field(default=None, alias='nextPageToken')

    _nonnull = field_validator('next_page_token', mode='before')(_reject_null)
