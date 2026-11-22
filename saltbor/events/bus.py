"""In-process event bus — publish/subscribe for simulation events."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from saltbor.events.types import EventType, SimulationEvent

logger = logging.getLogger(__name__)

# Type alias for event handler callbacks
EventHandler = Callable[[SimulationEvent], None]


@dataclass
class EventBus:
    """Simple synchronous pub/sub event bus.

    Any module can emit events. Handlers subscribe to specific event types
    or to all events (wildcard). Events are dispatched synchronously in
    registration order.
    """

    _handlers: dict[Optional[EventType], list[EventHandler]] = field(
        default_factory=lambda: defaultdict(list), init=False, repr=False
    )
    _event_log: list[SimulationEvent] = field(
        default_factory=list, init=False, repr=False
    )
    _max_log_size: int = 10_000
    _total_emitted_count: int = field(default=0, init=False, repr=False)

    # ---- Subscription ----

    def subscribe(
        self,
        event_type: Optional[EventType],
        handler: EventHandler,
    ) -> None:
        """Register a handler for a specific event type.

        Pass ``event_type=None`` to subscribe to *all* events (wildcard).
        """
        self._handlers[event_type].append(handler)
        logger.debug(
            "Handler %s subscribed to %s",
            getattr(handler, "__name__", handler),
            event_type,
        )

    def unsubscribe(
        self,
        event_type: Optional[EventType],
        handler: EventHandler,
    ) -> None:
        """Remove a handler."""
        try:
            self._handlers[event_type].remove(handler)
        except ValueError:
            pass

    # ---- Publishing ----

    def emit(self, event: SimulationEvent) -> None:
        """Emit an event to all matching handlers.

        Handlers for the specific event type are called first, then wildcard
        handlers (subscribed with ``event_type=None``).
        """
        # Log the event
        self._total_emitted_count += 1
        self._event_log.append(event)
        if len(self._event_log) > self._max_log_size:
            # Keep the most recent half
            self._event_log = self._event_log[self._max_log_size // 2 :]

        # Dispatch to specific handlers
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Handler %s failed for event %s",
                    getattr(handler, "__name__", handler),
                    event,
                )

        # Dispatch to wildcard handlers
        for handler in self._handlers.get(None, []):
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Wildcard handler %s failed for event %s",
                    getattr(handler, "__name__", handler),
                    event,
                )

    # ---- Inspection ----

    @property
    def event_log(self) -> list[SimulationEvent]:
        """Read-only view of the recent event log."""
        return list(self._event_log)

    @property
    def total_emitted_count(self) -> int:
        """Monotonic count of events emitted since initialization or last clear."""
        return self._total_emitted_count

    def events_since(self, cursor: int) -> tuple[list[SimulationEvent], int]:
        """Return events emitted since monotonic cursor without full-log copying or truncation drift."""
        new_count = self._total_emitted_count - max(0, cursor)
        if new_count <= 0:
            return [], self._total_emitted_count
        if new_count >= len(self._event_log):
            return list(self._event_log), self._total_emitted_count
        return self._event_log[-new_count:], self._total_emitted_count

    def events_of_type(self, event_type: EventType) -> list[SimulationEvent]:
        """Filter the event log by type."""
        return [e for e in self._event_log if e.event_type == event_type]

    def events_involving(self, human_id: object) -> list[SimulationEvent]:
        """Filter the event log for events involving a specific human."""
        return [e for e in self._event_log if e.involves(human_id)]  # type: ignore[arg-type]

    def clear_log(self) -> None:
        """Clear the in-memory event log."""
        self._event_log.clear()
        self._total_emitted_count = 0

    @property
    def handler_count(self) -> int:
        return sum(len(hs) for hs in self._handlers.values())
