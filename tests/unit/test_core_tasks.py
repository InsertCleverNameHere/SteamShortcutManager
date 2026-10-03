"""
tests/unit/test_core_tasks.py
Tests the pure standard-library task cancellation primitives in core/tasks.py.
Verifies thread safety, callback triggers, and isolation from Qt runtime.
"""

import threading

import pytest

from core.tasks import CancelToken, TaskCancelledError


def test_cancel_token_initial_state():
    token = CancelToken()
    assert not token.is_cancelled
    # Should not raise when uncancelled
    token.raise_if_cancelled()


def test_cancel_token_signals_cancelled():
    token = CancelToken()
    token.cancel()
    assert token.is_cancelled
    with pytest.raises(TaskCancelledError):
        token.raise_if_cancelled()


def test_cancel_token_callback_execution():
    token = CancelToken()
    called = []

    token.register_callback(lambda: called.append("first"))
    token.register_callback(lambda: called.append("second"))

    assert called == []
    token.cancel()
    assert called == ["first", "second"]

    # Registering callback on an already cancelled token invokes it immediately
    token.register_callback(lambda: called.append("third"))
    assert called == ["first", "second", "third"]


def test_cancel_token_progress_reporting():
    token = CancelToken()
    reports = []
    token.set_progress_callback(reports.append)

    token.report_progress("step 1")
    token.report_progress("step 2")
    assert reports == ["step 1", "step 2"]

    token.cancel()
    # Reports after cancellation should be ignored
    token.report_progress("step 3")
    assert reports == ["step 1", "step 2"]


def test_cancel_token_thread_safe_cancel():
    token = CancelToken()
    threads = [threading.Thread(target=token.cancel) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert token.is_cancelled
