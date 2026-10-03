"""
core/tasks.py
Pure Python cancellation primitives and task protocols.
Standard library only (threading) with zero UI or Qt dependencies,
allowing core modules to coordinate cancellation without GUI couplings.
"""

import threading
from collections.abc import Callable
from typing import Any, Protocol


class TaskCancelledError(Exception):
    """Raised by tasks when cooperative cancellation is requested."""


class CancelToken:
    """
    Thread-safe cancellation token and progress proxy passed to background tasks.
    """

    def __init__(self):
        self._event = threading.Event()
        self._progress_callback: Callable[[Any], None] | None = None
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Registers a callback to execute immediately upon cancellation (e.g. socket abort)."""
        with self._lock:
            if self._event.is_set():
                should_call = True
            else:
                self._callbacks.append(callback)
                should_call = False
        if should_call:
            try:
                callback()
            except Exception:
                pass

    def cancel(self) -> None:
        """Signals that cancellation has been requested and invokes registered abort hooks."""
        with self._lock:
            self._event.set()
            callbacks_to_run = list(self._callbacks)
            self._callbacks.clear()

        for cb in callbacks_to_run:
            try:
                cb()
            except Exception:
                pass

    @property
    def is_cancelled(self) -> bool:
        """Returns True if cancel() has been called."""
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        """Raises TaskCancelledError if cancellation has been requested."""
        if self.is_cancelled:
            raise TaskCancelledError("Operation was cancelled.")

    def set_progress_callback(self, callback: Callable[[Any], None] | None) -> None:
        self._progress_callback = callback

    def report_progress(self, data: Any) -> None:
        """Thread-safely forwards progress updates to the callback if registered."""
        if self._progress_callback and not self.is_cancelled:
            self._progress_callback(data)


class Task(Protocol):
    """Protocol that background tasks implement."""

    def run(self, token: CancelToken) -> Any: ...
