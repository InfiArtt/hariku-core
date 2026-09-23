# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import logging

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        self._listeners = {}

    def subscribe(self, event_name, callback):
        """Register a function to listen for an event."""
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        if callback not in self._listeners[event_name]:
            self._listeners[event_name].append(callback)
            logger.debug(f"Subscribed {callback.__name__} to event: {event_name}")

    def emit(self, event_name, *args, **kwargs):
        """Broadcast an event to all registered listeners."""
        if event_name in self._listeners:
            logger.debug(f"Emitting event: {event_name} to {len(self._listeners[event_name])} listeners")
            for callback in self._listeners[event_name]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error executing callback for event {event_name}: {e}")

# Global Event Bus instance
bus = EventBus()
