# -*- coding: utf-8 -*-
"""
:Module:            tests.unit.test_mcp_protocol
:Synopsis:          Exercise the optional MCP adapter through its installed stdio command
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.2 Astra)
:Modified Date:     18 Nov 2026
"""

import asyncio
import runpy
from pathlib import Path

import pytest


def test_mcp_stdio_contract(tmp_path):
    pytest.importorskip('mcp', reason='MCP protocol tests require the mcp extra.')
    harness = Path(__file__).resolve().parents[1] / 'offline' / 'mcp_qualification.py'
    asyncio.run(runpy.run_path(str(harness))['check'](tmp_path))
