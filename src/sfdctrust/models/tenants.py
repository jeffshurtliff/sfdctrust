# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.models.tenants
:Synopsis:          Typed tenant response models
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     03 Nov 2026
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._wire import _reject_null, _WireModel
from .events import EventSummary

__all__ = ['Tenant', 'TenantListResponse', 'TenantDetail', 'TenantLocation']


class Tenant(BaseModel):
    """An authorized tenant with opaque string identifiers and cloud values."""

    model_config = ConfigDict(strict=True, extra='allow')

    id: str
    cloud: str
    name: str
    environment: str | None = None
    my_domain: str | None = Field(default=None, alias='myDomain')

    @field_validator('environment', 'my_domain')
    @classmethod
    def _reject_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError('Tenant fields may be omitted but cannot be null.')
        return value


class TenantListResponse(BaseModel):
    """One page of authorized tenants and an optional opaque continuation token."""

    model_config = ConfigDict(strict=True, extra='allow')

    tenants: list[Tenant] = Field(max_length=200)
    next_page_token: str | None = Field(default=None, alias='nextPageToken')

    @field_validator('next_page_token')
    @classmethod
    def _reject_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError('The continuation token may be omitted but cannot be null.')
        return value


class TenantLocation(_WireModel):
    """Physical location of the primary instance, if available."""

    city: str
    state_name: str = Field(alias='stateName')
    state_code: str = Field(alias='stateCode')
    country_name: str = Field(alias='countryName')
    country_code: str = Field(alias='countryCode')


class TenantDetail(Tenant):
    """An authorized tenant with optional instance fields and embedded event history."""

    region: str | None = None
    version: str | None = None
    maintenance_window: str | None = Field(default=None, alias='maintenanceWindow')
    location: TenantLocation | None = None
    events: list[EventSummary]

    _nonnull = field_validator('location', mode='before')(_reject_null)
