# -*- coding: utf-8 -*-
"""
:Module:            tests.offline.sitecustomize
:Synopsis:          Inherited outbound network guard for behavioral qualification
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     13 Nov 2026
"""

import ipaddress
import sys


def deny_outbound(event, arguments):
    """Allow local IPC, but reject external connections and DNS before I/O."""
    if event in {'socket.connect', 'socket.bind', 'socket.sendto', 'socket.sendmsg'}:
        address = arguments[-1]
        if isinstance(address, tuple):
            try:
                local = ipaddress.ip_address(address[0]).is_loopback
            except ValueError:
                local = False
            if not local:
                raise RuntimeError('Outbound networking is disabled during behavioral qualification.')
    elif event in {'socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr'}:
        raise RuntimeError('DNS is disabled during behavioral qualification.')


sys.addaudithook(deny_outbound)
