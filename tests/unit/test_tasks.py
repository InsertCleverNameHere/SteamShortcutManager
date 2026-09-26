import time

from ui.tasks import CancelToken, Task, TaskRunner


class SimpleSuccessTask(Task):
    def run(self, token: CancelToken) -> str:
        return "task_success"


class FailingTask(Task):
    def run(self, token: CancelToken) -> None:
        raise ValueError("Simulated task error")


class CancellableTask(Task):
    def run(self, token: CancelToken) -> int:
        count = 0
        for _ in range(50):
            token.raise_if_cancelled()
            time.sleep(0.01)
            count += 1
            token.report_progress(f"step_{count}")
        return count


def test_task_runner_success(qtbot):
    runner = TaskRunner()
    results = []

    runner.start(
        SimpleSuccessTask(),
        key="test_success",
        on_result=lambda res: results.append(res),
    )

    qtbot.waitUntil(lambda: len(results) == 1, timeout=3000)
    assert results == ["task_success"]
    assert runner.active_task_count == 0


def test_task_runner_failure(qtbot):
    runner = TaskRunner()
    errors = []

    runner.start(
        FailingTask(),
        key="test_fail",
        on_error=lambda err: errors.append(err),
    )

    qtbot.waitUntil(lambda: len(errors) == 1, timeout=3000)
    assert isinstance(errors[0], ValueError)
    assert str(errors[0]) == "Simulated task error"
    assert runner.active_task_count == 0


def test_task_runner_cancellation(qtbot):
    runner = TaskRunner()
    cancelled_flags = []

    token = runner.start(
        CancellableTask(),
        key="test_cancel",
        on_cancelled=lambda: cancelled_flags.append(True),
    )

    # Cancel immediately while running
    time.sleep(0.03)
    token.cancel()

    qtbot.waitUntil(lambda: len(cancelled_flags) == 1, timeout=3000)
    assert cancelled_flags == [True]
    assert runner.active_task_count == 0


def test_task_runner_keyed_replacement(qtbot):
    runner = TaskRunner()
    cancelled_count = [0]
    results = []

    # Start long task with key "search"
    runner.start(
        CancellableTask(),
        key="search",
        on_cancelled=lambda: cancelled_count.__setitem__(0, cancelled_count[0] + 1),
    )

    # Replace immediately with a fast success task using the same key
    runner.start(
        SimpleSuccessTask(),
        key="search",
        on_result=lambda res: results.append(res),
    )

    qtbot.waitUntil(lambda: len(results) == 1, timeout=3000)
    assert results == ["task_success"]
    # The first task must have been cancelled
    qtbot.waitUntil(lambda: cancelled_count[0] == 1, timeout=3000)
    assert runner.active_task_count == 0


def test_task_runner_progress(qtbot):
    runner = TaskRunner()
    progress_updates = []
    results = []

    runner.start(
        CancellableTask(),
        key="test_progress",
        on_progress=lambda p: progress_updates.append(p),
        on_result=lambda res: results.append(res),
    )

    qtbot.waitUntil(lambda: len(results) == 1, timeout=3000)
    assert len(progress_updates) > 0
    assert "step_1" in progress_updates


def test_task_runner_shutdown(qtbot):
    runner = TaskRunner()
    runner.start(CancellableTask(), key="task1")
    runner.start(CancellableTask(), key="task2")

    assert runner.active_task_count == 2
    runner.shutdown(timeout_ms=1000)
    assert runner.active_task_count == 0
