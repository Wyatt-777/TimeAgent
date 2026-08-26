"""Thread-safe event queue connecting sensors to runtime services."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Lock

from .event import Event


class EventBus:
    """A small in-process event bus backed by :class:`queue.Queue`."""

    _STOP = object()

    def __init__(self, maxsize: int = 0) -> None:
        if maxsize < 0:
            raise ValueError("maxsize cannot be negative")
        self._queue: Queue[Event | object] = Queue(maxsize=maxsize)
        self._lock = Lock()
        self._closed = False

    def publish(self, event: Event) -> None:
        """Publish an event unless the bus has been shut down."""
        if not isinstance(event, Event):
            raise TypeError("EventBus accepts Event instances only")
        with self._lock:
            if self._closed:
                raise RuntimeError("EventBus is shut down")
            self._queue.put(event)

    def consume(self, timeout: float | None = None) -> Event | None:
        """Consume the next event, returning ``None`` on timeout or shutdown."""
        try:
            item = self._queue.get(timeout=timeout)
        except Empty:
            return None
        if item is self._STOP:
            return None
        return item

    def shutdown(self) -> None:
        """Stop accepting events and wake a blocked consumer."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._queue.put(self._STOP)

    @property
    def is_shutdown(self) -> bool:
        return self._closed

    def qsize(self) -> int:
        """Return the approximate number of queued items."""
        return self._queue.qsize()
