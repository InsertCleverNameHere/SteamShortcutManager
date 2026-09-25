"""
ui/tasks.py
Hardened background task execution framework for PySide6.
Provides CancelToken, keyed task deduplication, clean cancellation,
guaranteed exactly-once terminal signal emission, and safe shutdown.
"""

import threading
from collections.abc import Callable
from typing import Any, Protocol

from PySide6 import QtCore

from core.log import get_logger

logger = get_logger("tasks")


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
        """Thread-safely forwards progress updates to the UI callback if registered."""
        if self._progress_callback and not self.is_cancelled:
            self._progress_callback(data)


class Task(Protocol):
    """Protocol that background tasks implement."""

    def run(self, token: CancelToken) -> Any: ...


class _TaskWorker(QtCore.QObject):
    """
    Internal QObject that runs the Task in a background QThread
    and guarantees exactly one terminal signal emission.
    """

    result_ready = QtCore.Signal(object)
    error_raised = QtCore.Signal(object)
    cancelled = QtCore.Signal()
    progress_update = QtCore.Signal(object)

    def __init__(self, task: Task, token: CancelToken, task_name: str):
        super().__init__()
        self.task = task
        self.token = token
        self.task_name = task_name
        self.token.set_progress_callback(self.progress_update.emit)

    def run(self) -> None:
        """Executes the task with strict exactly-once terminal signal emission."""
        try:
            if self.token.is_cancelled:
                self.cancelled.emit()
                return

            result = self.task.run(self.token)

            if self.token.is_cancelled:
                self.cancelled.emit()
            else:
                self.result_ready.emit(result)

        except TaskCancelledError:
            self.cancelled.emit()
        except Exception as exc:
            logger.exception(
                f"Unhandled exception in background task '{self.task_name}': {exc}"
            )
            self.error_raised.emit(exc)


class TaskRunner(QtCore.QObject):
    """
    Manages background QThread lifecycles, keyed deduplication, and safe shutdown.
    """

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        # Keyed active tasks: key -> (CancelToken, QThread, _TaskWorker)
        self._keyed_tasks: dict[
            str, tuple[CancelToken, QtCore.QThread, _TaskWorker]
        ] = {}
        # Anonymous active tasks: set of (CancelToken, QThread, _TaskWorker)
        self._anonymous_tasks: set[tuple[CancelToken, QtCore.QThread, _TaskWorker]] = (
            set()
        )
        self._lock = threading.Lock()

    @property
    def active_task_count(self) -> int:
        """Returns the total number of running background tasks."""
        with self._lock:
            return len(self._keyed_tasks) + len(self._anonymous_tasks)

    def start(
        self,
        task: Task,
        key: str | None = None,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
        on_progress: Callable[[Any], None] | None = None,
        name: str | None = None,
    ) -> CancelToken:
        """
        Launches a background Task on a managed QThread.

        If a task with the same `key` is already running, it is signalled to cancel
        before the new task begins.
        """
        task_name = name or key or task.__class__.__name__

        # 1. Cancel previous task if key is already active
        if key:
            self.cancel(key)

        token = CancelToken()
        thread = QtCore.QThread()
        thread.setObjectName(f"ssm-{task_name}")

        worker = _TaskWorker(task, token, task_name)
        worker.moveToThread(thread)

        entry = (token, thread, worker)

        with self._lock:
            if key:
                self._keyed_tasks[key] = entry
            else:
                self._anonymous_tasks.add(entry)

        # 2. Wire callbacks
        if on_result:
            worker.result_ready.connect(on_result)
        if on_error:
            worker.error_raised.connect(on_error)
        if on_cancelled:
            worker.cancelled.connect(on_cancelled)
        if on_progress:
            worker.progress_update.connect(on_progress)

        # 3. Exactly-once terminal lifecycle wiring
        thread.started.connect(worker.run)

        def _cleanup():
            with self._lock:
                if key and self._keyed_tasks.get(key) == entry:
                    self._keyed_tasks.pop(key, None)
                self._anonymous_tasks.discard(entry)

        # Stop thread loop after terminal signal
        worker.result_ready.connect(thread.quit)
        worker.error_raised.connect(thread.quit)
        worker.cancelled.connect(thread.quit)

        # Deregister task immediately upon terminal signal emission
        worker.result_ready.connect(_cleanup)
        worker.error_raised.connect(_cleanup)
        worker.cancelled.connect(_cleanup)

        thread.finished.connect(_cleanup)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()
        return token

    def cancel(self, key: str) -> None:
        """Requests cancellation for the active task matching key, if present."""
        with self._lock:
            entry = self._keyed_tasks.get(key)
        if entry:
            token, _, _ = entry
            token.cancel()

    def cancel_all(self) -> None:
        """Signals cancellation to all currently running tasks."""
        with self._lock:
            all_entries = list(self._keyed_tasks.values()) + list(self._anonymous_tasks)
        for token, _, _ in all_entries:
            token.cancel()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """
        Gracefully terminates all active threads during screen switch or window close.
        Cancels all tokens, quits thread loops, and waits up to timeout_ms.
        """
        with self._lock:
            all_entries = list(self._keyed_tasks.values()) + list(self._anonymous_tasks)

        # Signal cancellation to all workers
        for token, thread, _ in all_entries:
            token.cancel()
            if thread.isRunning():
                thread.quit()

        # Wait on each running thread up to divided slice
        for _, thread, _ in all_entries:
            if thread.isRunning():
                if not thread.wait(timeout_ms):
                    logger.warning(
                        f"Background thread '{thread.objectName()}' did not stop within {timeout_ms}ms"
                    )

        with self._lock:
            self._keyed_tasks.clear()
            self._anonymous_tasks.clear()
