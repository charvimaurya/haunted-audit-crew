"""Test doubles for Night Watch: a fake API and a fake clock (no network, no waiting)."""
from __future__ import annotations

try:
    from night_watch.models import RunSnapshot
except ImportError:  # running from inside the night_watch folder
    from models import RunSnapshot


def running() -> RunSnapshot:
    """A snapshot for a run that is still going."""
    return RunSnapshot("running", None, None)


def complete(verdict, reason_code=None) -> RunSnapshot:
    """A snapshot for a finished run."""
    return RunSnapshot("complete", verdict, reason_code)


class FakeApi:
    """Same interface as ApiClient, driven by scripted answers.

    starts: {variant: [run_id or Exception, ...]} answers for start_run.
    polls:  {variant: [RunSnapshot or Exception, ...]} answers for get_run.
    A variant with no start script gets auto run ids (run-1, run-2, ...).
    Each script is used in order; when it runs out, its last item repeats.
    Every call is appended to self.calls as a tuple, in order:
    ("start_run", variant) or ("get_run", run_id).
    """

    def __init__(self, starts=None, polls=None):
        self.starts = {k: list(v) for k, v in (starts or {}).items()}
        self.polls = {k: list(v) for k, v in (polls or {}).items()}
        self.calls: list[tuple[str, str]] = []
        self._run_variant: dict[str, str] = {}
        self._auto_ids = 0
        self._start_pos: dict[str, int] = {}
        self._poll_pos: dict[str, int] = {}

    @staticmethod
    def _next(script: list, pos: dict, key: str):
        """Take the next scripted item for key; repeat the last one when used up."""
        index = pos.get(key, 0)
        pos[key] = index + 1
        return script[min(index, len(script) - 1)]

    def start_run(self, variant: str) -> str:
        self.calls.append(("start_run", variant))
        script = self.starts.get(variant)
        if script:
            item = self._next(script, self._start_pos, variant)
        else:
            self._auto_ids += 1
            item = f"run-{self._auto_ids}"
        if isinstance(item, BaseException):
            raise item
        self._run_variant[item] = variant
        return item

    def get_run(self, run_id: str) -> RunSnapshot:
        self.calls.append(("get_run", run_id))
        variant = self._run_variant.get(run_id)
        script = self.polls.get(variant)
        if not script:
            raise AssertionError(f"no poll script for run {run_id!r}")
        item = self._next(script, self._poll_pos, variant)
        if isinstance(item, BaseException):
            raise item
        return item

    def calls_named(self, name: str) -> list[str]:
        """Arguments of every call to one method, in order."""
        return [arg for method, arg in self.calls if method == name]


class FakeClock:
    """Fake clock: sleep records the duration and moves time forward."""

    def __init__(self, start: float = 1000.0):
        self._now = float(start)
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._now += seconds

    def now(self) -> float:
        return self._now

    def total_slept(self) -> float:
        return sum(self.sleeps)
