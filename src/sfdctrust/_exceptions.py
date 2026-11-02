# -*- coding: utf-8 -*-
"""
:Module:            sfdctrust._exceptions
:Synopsis:          Exception classes that are utilized throughout the package
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6)
:Modified Date:     01 Nov 2026
"""

from __future__ import annotations

__all__ = ['TrustCenterError']


class TrustCenterError(Exception):
    """Base class for sfdctrust exceptions."""
