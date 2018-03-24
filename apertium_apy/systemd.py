#!/usr/bin/env python3
# coding=utf-8
# -*- indent-tabs-mode: nil -*-
# -*- encoding: utf-8 -*-

"""
Copyright (C) 2016 Kevin Brubeck Unhammer
based on https://gist.github.com/Spindel/1d07533ef94a4589d348 / watchdogged.py
Copyright (C) 2015 D.S. Ljungmark, Modio AB
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import logging
import socket
import os

# All singletons are prefixed "the"
the_log = logging.getLogger(__name__)


def watchdog_period():
    """Return the time (in seconds) that we need to ping within."""
    val = os.environ.get('WATCHDOG_USEC', None)
    if not val:
        return None
    return int(val) / 1000000


def notify_socket(clean_environment=True):
    """Return a tuple of address, socket for future use.
    clean_environment removes the variables from env to prevent children
    from inheriting it and doing something wrong.
    """
    _empty = None, None
    address = os.environ.get('NOTIFY_SOCKET', None)
    if clean_environment:
        address = os.environ.pop('NOTIFY_SOCKET', None)

    if not address:
        return _empty

    if len(address) == 1:
        return _empty

    if address[0] not in ('@', '/'):
        return _empty

    if address[0] == '@':
        address = '\0' + address[1:]

    # SOCK_CLOEXEC was added in Python 3.2 and requires Linux >= 2.6.27.
    # It means "close this socket after fork/exec()
    try:
        sock = socket.socket(socket.AF_UNIX,
                             socket.SOCK_DGRAM | socket.SOCK_CLOEXEC)
    except AttributeError:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

    return address, sock


class Watchdog(object):

    def __init__(self, period, address, sock):
        # "The daemon should then issue sd_notify("WATCHDOG=1") calls every half of that interval."
        self.period = float(period) / 2.0
        self.address = address
        self.sock = sock

    def __del__(self):
        self.systemd_stop()

    def sd_message(self, message):
        """Send a message to the systemd bus/socket.
        message is expected to be bytes.
        """
        if not (self.address and self.sock and message):
            the_log.info("Couldn't message! {} {} {}".format(self.address, self.sock, message))
            return False
        assert isinstance(message, bytes)

        try:
            retval = self.sock.sendto(message, self.address)
        except socket.error:
            return False
        return (retval > 0)

    def watchdog_ping(self):
        """Helper function to send a watchdog ping."""
        return self.sd_message(b'WATCHDOG=1')

    def systemd_ready(self):
        """Helper function to send a ready signal."""
        return self.sd_message(b'READY=1')

    def systemd_stop(self):
        """Helper function to signal service stopping."""
        return self.sd_message(b'STOPPING=1')


def setup_watchdog():
    # Get our settings from the environment
    notify = notify_socket()
    period = watchdog_period()
    # Validate some in-data
    if not notify[0]:
        the_log.info('No notification socket, not launched via systemd?')
        return None
    if not period:
        the_log.warning('Found systemd notification socket, but no watchdog period set in the unit file!')
        return None
    wd = Watchdog(period, *notify)
    return wd
