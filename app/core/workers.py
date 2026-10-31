"""Thread → GUI event plumbing.

Tkinter is single threaded: worker threads must never touch widgets.  A
:class:`BackgroundJob` runs ``func(emitter)`` on a daemon thread, pushes log,
progress and result events into a :class:`queue.Queue`, and the view polls it
from an ``after()`` callback.  The same job can also be executed synchronously
(:meth:`BackgroundJob.run_sync`), which is how the tests drive it.
"""

from __future__ import annotations

import queue
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

EventKind = Literal["log", "progress", "result", "error", "cancelled"]


@dataclass
class JobEvent:
    """One event produced by a background job."""

    kind: EventKind
    payload: Any = None
    detail: str = ""


@dataclass
class Progress:
    """Progress payload carried by :attr:`JobEvent.payload` for progress events."""

    current: int
    total: int
    label: str = field(default="")

    @property
    def fraction(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(1.0, self.current / self.total))


class JobCancelledError(RuntimeError):
    """Raised inside a worker when the user cancels the job."""


class Emitter:
    """Bridge handed to worker callables."""

    def __init__(self, sink: Callable[[JobEvent], None], cancel_event: threading.Event) -> None:
        self._sink = sink
        self._cancel = cancel_event

    def __call__(self, *args: Any) -> None:
        """Accept both ``emit("message")`` and ``emit("progress", 1, 4, "label")``.

        This lets the same emitter be handed to the core session (whose Emit
        protocol uses the ``"progress"`` marker) and used directly for logging.
        """
        if len(args) == 1:
            self.log(str(args[0]))
            return
        if args and args[0] == "progress":
            current = args[1] if len(args) > 1 else 0
            total = args[2] if len(args) > 2 else 0
            label = args[3] if len(args) > 3 else ""
            self.progress(current, total, label)
            return
        self.log(" ".join(str(arg) for arg in args))

    def log(self, message: str) -> None:
        self._sink(JobEvent("log", str(message)))

    def progress(self, current: int, total: int, label: str = "") -> None:
        self._sink(JobEvent("progress", Progress(int(current), int(total), label)))

    def check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise JobCancelledError("Operation cancelled")

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


WorkerFunc = Callable[[Emitter], Any]


class BackgroundJob:
    """A unit of work with an event queue."""

    def __init__(self, func: WorkerFunc, name: str = "job") -> None:
        self.func = func
        self.name = name
        self._queue: queue.Queue[JobEvent] = queue.Queue()
        self.history: list[JobEvent] = []
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self.finished = False
        self.result: Any = None
        self.error: BaseException | None = None

    # ------------------------------------------------------------------
    def _emit(self, event: JobEvent) -> None:
        self.history.append(event)
        self._queue.put(event)

    def _run(self) -> None:
        emitter = Emitter(self._emit, self._cancel)
        try:
            value = self.func(emitter)
        except JobCancelledError as exc:
            self._emit(JobEvent("cancelled", str(exc)))
            self.error = exc
        except BaseException as exc:  # noqa: BLE001 - surfaced to the UI
            self.error = exc
            detail = traceback.format_exc(limit=4)
            self._emit(JobEvent("error", exc, detail))
        else:
            self.result = value
            self._emit(JobEvent("result", value))
        finally:
            self.finished = True

    def start(self) -> BackgroundJob:
        """Start the job on a daemon thread."""
        self._thread = threading.Thread(target=self._run, name=f"gd-{self.name}", daemon=True)
        self._thread.start()
        return self

    def run_sync(self) -> list[JobEvent]:
        """Run the job on the calling thread and return every event.

        The queue is left intact so a UI that polls afterwards (the normal
        ``after()`` path) still sees each event exactly once.
        """
        self._run()
        return list(self.history)

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def drain(self) -> list[JobEvent]:
        """Return (and remove) every event queued so far."""
        events: list[JobEvent] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def poll(self) -> list[JobEvent]:
        """Alias of :meth:`drain` used by the ``after()`` loop."""
        return self.drain()


def collect_logs(events: list[JobEvent]) -> list[str]:
    """Convenience for tests: every log message in order."""
    return [str(event.payload) for event in events if event.kind == "log"]


def final_result(events: list[JobEvent]) -> Any:
    """The payload of the last ``result`` event, or ``None``."""
    result = None
    for event in events:
        if event.kind == "result":
            result = event.payload
    return result


def first_error(events: list[JobEvent]) -> BaseException | None:
    for event in events:
        if event.kind == "error" and isinstance(event.payload, BaseException):
            return event.payload
    return None


__all__ = [
    "BackgroundJob",
    "Emitter",
    "EventKind",
    "JobCancelledError",
    "JobEvent",
    "Progress",
    "WorkerFunc",
    "collect_logs",
    "final_result",
    "first_error",
]
