# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Tests for core.events — EventBus pub/sub system
# =============================================================================

import pytest


class TestEventBusSubscribe:
    """Tests for EventBus.subscribe()"""

    def test_subscribe_registers_callback(self, fresh_event_bus):
        """A subscribed callback should appear in the listener registry."""
        bus = fresh_event_bus
        handler = lambda: None
        bus.subscribe("test_event", handler)
        assert handler in bus._listeners["test_event"]

    def test_subscribe_duplicate_ignored(self, fresh_event_bus):
        """Subscribing the same callback twice should not duplicate it."""
        bus = fresh_event_bus
        handler = lambda: None
        bus.subscribe("test_event", handler)
        bus.subscribe("test_event", handler)
        assert len(bus._listeners["test_event"]) == 1

    def test_subscribe_multiple_handlers(self, fresh_event_bus):
        """Multiple different callbacks can subscribe to the same event."""
        bus = fresh_event_bus
        h1 = lambda: None
        h2 = lambda: None
        bus.subscribe("test_event", h1)
        bus.subscribe("test_event", h2)
        assert len(bus._listeners["test_event"]) == 2

    def test_subscribe_different_events(self, fresh_event_bus):
        """Callbacks on different event names are independent."""
        bus = fresh_event_bus
        h1 = lambda: None
        h2 = lambda: None
        bus.subscribe("event_a", h1)
        bus.subscribe("event_b", h2)
        assert "event_a" in bus._listeners
        assert "event_b" in bus._listeners
        assert h1 not in bus._listeners.get("event_b", [])


class TestEventBusEmit:
    """Tests for EventBus.emit()"""

    def test_emit_fires_callback(self, fresh_event_bus):
        """Emitting an event should call all registered callbacks."""
        bus = fresh_event_bus
        results = []
        bus.subscribe("ping", lambda: results.append("pong"))
        bus.emit("ping")
        assert results == ["pong"]

    def test_emit_passes_args(self, fresh_event_bus):
        """Callbacks should receive the args passed to emit."""
        bus = fresh_event_bus
        received = []
        bus.subscribe("data", lambda x, y: received.extend([x, y]))
        bus.emit("data", 42, "hello")
        assert received == [42, "hello"]

    def test_emit_passes_kwargs(self, fresh_event_bus):
        """Callbacks should receive kwargs passed to emit."""
        bus = fresh_event_bus
        received = {}
        bus.subscribe("config", lambda **kw: received.update(kw))
        bus.emit("config", theme="dark", lang="id")
        assert received == {"theme": "dark", "lang": "id"}

    def test_emit_no_subscribers_no_crash(self, fresh_event_bus):
        """Emitting an event with no subscribers should not raise."""
        bus = fresh_event_bus
        bus.emit("nobody_listens")  # Should not raise

    def test_emit_exception_in_handler_does_not_break_others(self, fresh_event_bus):
        """If one handler raises, other handlers should still fire."""
        bus = fresh_event_bus
        results = []

        def bad_handler():
            raise RuntimeError("I broke!")

        def good_handler():
            results.append("ok")

        bus.subscribe("fragile", bad_handler)
        bus.subscribe("fragile", good_handler)
        bus.emit("fragile")
        assert results == ["ok"]

    def test_emit_fires_multiple_handlers_in_order(self, fresh_event_bus):
        """Handlers should fire in the order they were subscribed."""
        bus = fresh_event_bus
        order = []
        bus.subscribe("ordered", lambda: order.append(1))
        bus.subscribe("ordered", lambda: order.append(2))
        bus.subscribe("ordered", lambda: order.append(3))
        bus.emit("ordered")
        assert order == [1, 2, 3]


class TestGlobalBusSingleton:
    """Tests for the global bus instance."""

    def test_global_bus_exists(self):
        """core.events should export a global `bus` instance."""
        from core.events import bus
        assert bus is not None

    def test_global_bus_is_event_bus(self):
        """The global `bus` should be an EventBus instance."""
        from core.events import bus, EventBus
        assert isinstance(bus, EventBus)
