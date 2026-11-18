"""In-memory broker for live review runs.

A run is a bounded, ordered event buffer plus a set of subscriber queues, so the
SSE endpoint can replay what a late/reconnecting browser missed and then follow
along live. Events are intentionally **not** persisted: only
``cv_reviews.run_state`` / ``run_error`` survive a restart.

Single-process assumption: the registry lives in this Python process, which is
why the app must run behind one uvicorn worker. If the process dies mid-run the
review is reconciled to ``failed`` the next time it is read (see
``routers/reviews.py``).
"""
import asyncio
import json
from typing import Dict, List, Optional

MAX_EVENTS = 2_000
MAX_BYTES = 256 * 1024
MAX_RUNS = 50
QUEUE_SIZE = 1_000
TERMINAL_TYPES = ("done", "error")


class ReviewRun:
    def __init__(self, review_id: int):
        self.review_id = review_id
        self.events: List[dict] = []
        self.seq = 0
        self.size = 0
        self.finished = False
        self.subscribers: List[asyncio.Queue] = []

    def _size_of(self, event: dict) -> int:
        return len(json.dumps(event, default=str))

    def add(self, event: dict) -> dict:
        self.seq += 1
        wrapped = {"seq": self.seq, **event}
        self.events.append(wrapped)
        self.size += self._size_of(wrapped)
        self._trim()
        return wrapped

    def _trim(self) -> None:
        """Drop the oldest delta first; fall back to dropping the oldest event."""
        while self.events and (
            len(self.events) > MAX_EVENTS or self.size > MAX_BYTES
        ):
            index = next(
                (i for i, ev in enumerate(self.events) if ev.get("type") == "delta"),
                0,
            )
            dropped = self.events.pop(index)
            self.size = max(0, self.size - self._size_of(dropped))

    def publish(self, event: Optional[dict]) -> None:
        # ``None`` is the end-of-run sentinel for subscribers.
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass


_runs: Dict[int, ReviewRun] = {}
_tasks: Dict[int, asyncio.Task] = {}


def _evict_finished() -> None:
    if len(_runs) <= MAX_RUNS:
        return
    for review_id, run in list(_runs.items()):
        if len(_runs) <= MAX_RUNS:
            break
        if run.finished:
            _runs.pop(review_id, None)


def open_run(review_id: int) -> ReviewRun:
    """Start a run. Called synchronously by the POST handler before the task
    starts, so an immediate SSE connection always finds it."""
    run = ReviewRun(review_id)
    _runs[review_id] = run
    _evict_finished()
    return run


def get_run(review_id: int) -> Optional[ReviewRun]:
    return _runs.get(review_id)


def active(review_id: int) -> bool:
    run = _runs.get(review_id)
    return bool(run and not run.finished)


def emit(review_id: int, event: dict) -> Optional[dict]:
    """Append an event and fan it out. Returns the sequenced event."""
    run = _runs.get(review_id)
    if run is None or run.finished:
        return None
    wrapped = run.add(event)
    run.publish(wrapped)
    return wrapped


def snapshot(review_id: int) -> List[dict]:
    run = _runs.get(review_id)
    return list(run.events) if run else []


def subscribe(review_id: int) -> Optional[asyncio.Queue]:
    run = _runs.get(review_id)
    if run is None:
        return None
    queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
    run.subscribers.append(queue)
    return queue


def unsubscribe(review_id: int, queue: asyncio.Queue) -> None:
    run = _runs.get(review_id)
    if run and queue in run.subscribers:
        run.subscribers.remove(queue)


def finish_run(review_id: int) -> None:
    """Mark a run finished and wake every subscriber."""
    run = _runs.get(review_id)
    if run is not None:
        run.finished = True
        run.publish(None)
    _tasks.pop(review_id, None)


def register_task(review_id: int, task: asyncio.Task) -> None:
    # Keep a strong reference so the task cannot be garbage collected mid-run.
    _tasks[review_id] = task
