# hariku2/core/events.py
import logging

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        self._listeners = {}

    def subscribe(self, event_name, callback):
        """Mendaftarkan fungsi untuk mendengarkan sebuah event."""
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        if callback not in self._listeners[event_name]:
            self._listeners[event_name].append(callback)
            logger.debug(f"Subscribed {callback.__name__} to event: {event_name}")

    def emit(self, event_name, *args, **kwargs):
        """Menyiarkan event ke semua pendengar yang terdaftar."""
        if event_name in self._listeners:
            logger.debug(f"Emitting event: {event_name} to {len(self._listeners[event_name])} listeners")
            for callback in self._listeners[event_name]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error executing callback for event {event_name}: {e}")

# Global Event Bus instance
bus = EventBus()
