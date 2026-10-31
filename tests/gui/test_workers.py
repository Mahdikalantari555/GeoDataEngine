"""Tests for ``app.core.workers`` — thread → GUI event plumbing."""

from __future__ import annotations

import time

import pytest
from app.core.workers import (
    BackgroundJob,
    Emitter,
    JobCancelledError,
    JobEvent,
    Progress,
    collect_logs,
    final_result,
    first_error,
)


class TestProgress:
    def test_fraction(self):
        assert Progress(1, 4).fraction == 0.25
        assert Progress(4, 4).fraction == 1.0
        assert Progress(0, 0).fraction == 0.0

    def test_fraction_is_clamped(self):
        assert Progress(9, 4).fraction == 1.0
        assert Progress(-1, 4).fraction == 0.0


class TestBackgroundJobSync:
    def test_emits_log_progress_and_result(self):
        def work(emit: Emitter):
            emit.log("starting")
            emit.progress(1, 2, "half")
            emit.log("finishing")
            return {"answer": 42}

        job = BackgroundJob(work, "sync")
        events = job.run_sync()

        assert [event.kind for event in events] == ["log", "progress", "log", "result"]
        assert collect_logs(events) == ["starting", "finishing"]
        assert final_result(events) == {"answer": 42}
        assert events[1].payload.fraction == 0.5
        assert job.finished is True
        assert job.error is None

    def test_events_are_not_lost_for_a_late_poller(self):
        """``run_sync`` must leave the queue intact for the UI to drain."""
        job = BackgroundJob(lambda emit: emit.log("hello"), "sync")
        history = job.run_sync()
        drained = job.poll()
        assert collect_logs(history) == ["hello"]
        assert collect_logs(drained) == ["hello"]
        assert job.poll() == []

    def test_error_is_captured_not_raised(self):
        def work(emit: Emitter):
            raise ValueError("boom")

        job = BackgroundJob(work, "failing")
        events = job.run_sync()

        error = first_error(events)
        assert isinstance(error, ValueError)
        assert job.error is error
        assert job.finished is True
        error_event = [event for event in events if event.kind == "error"][0]
        assert "ValueError: boom" in error_event.detail

    def test_cancellation_is_reported(self):
        def work(emit: Emitter):
            emit.check_cancelled()
            raise AssertionError("should not reach this line")

        job = BackgroundJob(work, "cancel")
        job.cancel()
        events = job.run_sync()
        assert events[-1].kind == "cancelled"
        assert isinstance(job.error, JobCancelledError)

    def test_cancel_event_stops_the_worker(self):
        def work(emit: Emitter):
            emit.log("step 1")
            emit.check_cancelled()
            emit.log("step 2")

        job = BackgroundJob(work, "cancel-mid")
        seen = []

        def work_and_cancel(emit: Emitter):
            emit.log("step 1")
            job.cancel()
            emit.check_cancelled()
            seen.append("step 2")

        job = BackgroundJob(work_and_cancel, "cancel-mid")
        job.run_sync()
        assert seen == []

    def test_emitter_cancelled_property(self):
        import threading

        event = threading.Event()
        emitter = Emitter(lambda _event: None, event)
        assert emitter.cancelled is False
        event.set()
        assert emitter.cancelled is True


class TestBackgroundJobThread:
    def test_runs_on_a_daemon_thread(self):
        import threading

        names = []

        def work(emit: Emitter):
            names.append(threading.current_thread().name)
            emit.log("done")
            return "ok"

        job = BackgroundJob(work, "threaded").start()
        job.join(timeout=5)

        assert job.finished is True
        assert job.result == "ok"
        assert names == ["gd-threaded"]
        assert job.is_alive is False

    def test_polling_sees_events(self):
        job = BackgroundJob(lambda emit: [emit.log(str(i)) for i in range(5)], "poll").start()
        job.join(timeout=5)
        assert len(job.poll()) == 6  # 5 logs + result

    def test_cancel_stops_a_long_job(self):
        def work(emit: Emitter):
            for _ in range(1000):
                emit.check_cancelled()
                time.sleep(0.001)
            return "never"

        job = BackgroundJob(work, "long").start()
        time.sleep(0.02)
        job.cancel()
        job.join(timeout=5)
        assert job.finished is True
        assert isinstance(job.error, JobCancelledError)

    def test_result_payload_types(self):
        job = BackgroundJob(lambda emit: [1, 2, 3], "list").start()
        job.join(timeout=5)
        events = job.poll()
        assert events[-1] == JobEvent("result", [1, 2, 3])


class TestHelpers:
    def test_first_error_returns_none_without_errors(self):
        job = BackgroundJob(lambda emit: emit.log("ok"), "ok")
        assert first_error(job.run_sync()) is None

    def test_final_result_returns_last_result(self):
        events = [JobEvent("result", 1), JobEvent("log", "x"), JobEvent("result", 2)]
        assert final_result(events) == 2

    def test_collect_logs_ignores_other_events(self):
        events = [JobEvent("log", "a"), JobEvent("progress", Progress(1, 2)), JobEvent("log", "b")]
        assert collect_logs(events) == ["a", "b"]


def test_job_records_history():
    job = BackgroundJob(lambda emit: emit.log("x"), "history")
    job.run_sync()
    assert [event.kind for event in job.history] == ["log", "result"]


def test_poll_is_empty_before_start():
    assert BackgroundJob(lambda emit: None, "idle").poll() == []


@pytest.mark.parametrize("name", ["download", "indices", "metric", "bootstrap"])
def test_job_names_are_preserved(name):
    job = BackgroundJob(lambda emit: None, name)
    assert job.name == name
