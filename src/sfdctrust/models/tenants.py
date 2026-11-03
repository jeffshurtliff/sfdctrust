# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust.models.tenants
:Synopsis:          Typed tenant-list response models
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     02 Nov 2026
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ['Tenant', 'TenantListResponse']


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
