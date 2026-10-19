"""Small synchronous event bus for decoupled application components.

Subscribers are called immediately in subscription order on the publisher's
call stack. The event bus is dependency-free and deliberately in-process; it
can notify components such as the GUI when workspace or link state changes.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

EventHandler = Callable[["Event"], None]


@dataclass(frozen=True)
class Event:
    """A single event published on the bus.

    Attributes:
        name: Event type identifier, e.g. ``"link.up"``. Convention:
            lowercase, dot-separated namespace.
        payload: Arbitrary event-specific data. Kept as a plain dict
            (rather than a subclass per event type) to keep event creation
            lightweight and allow producers to add payload fields as needed.
        source: Optional free-text identifier of what published the
            event (e.g. a device hostname), useful for logging/debugging.
    """

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str | None = None


class EventBus:
    """A simple synchronous publish/subscribe event bus.

    Example:
        >>> bus = EventBus()
        >>> received = []
        >>> unsubscribe = bus.subscribe("link.up", received.append)
        >>> bus.publish(Event(name="link.up", payload={"iface": "Gi0/0"}))
        >>> len(received)
        1
        >>> unsubscribe()
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> Callable[[], None]:
        """Register ``handler`` to be called for events named ``event_name``.

        Args:
            event_name: The exact event name to listen for.
            handler: A callable accepting a single :class:`Event` argument.

        Returns:
            A zero-argument callable that unsubscribes ``handler`` when called.
        """
        self._handlers[event_name].append(handler)

        def unsubscribe() -> None:
            try:
                self._handlers[event_name].remove(handler)
            except ValueError:
                pass

        return unsubscribe

    def publish(self, event: Event) -> None:
        """Publish an event, synchronously invoking all matching handlers.

        A handler that raises is logged and does not prevent other
        handlers from running — one broken subscriber should not be
        able to break the whole system.

        Args:
            event: The event to publish.
        """
        for handler in list(self._handlers.get(event.name, [])):
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Event handler for %r raised an exception", event.name
                )

    def clear(self, event_name: str | None = None) -> None:
        """Remove all subscribers, optionally scoped to one event name.

        Args:
            event_name: If given, only clear subscribers for this event
                name. If omitted, clear all subscribers for all events.
        """
        if event_name is None:
            self._handlers.clear()
        else:
            self._handlers.pop(event_name, None)
