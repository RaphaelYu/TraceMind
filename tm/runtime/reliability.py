from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event, Lock
from typing import Any, Callable, Dict, Iterable, Mapping


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StepTimeoutError(RuntimeError):
    """Raised when a step exceeds its configured timeout."""


class RunCancelledError(RuntimeError):
    """Raised when a cancellation request interrupts the run."""


@dataclass(frozen=True)
class StepReliabilityPolicy:
    """Defines timeout and retry bounds for a controller step."""

    timeout_seconds: float | None = None
    max_attempts: int = 1


@dataclass
class ReliabilityProfile:
    """Maps step names to their configured reliability policies."""

    default_policy: StepReliabilityPolicy = field(default_factory=StepReliabilityPolicy)
    step_policies: Dict[str, StepReliabilityPolicy] = field(default_factory=dict)

    def policy_for_step(self, step_name: str) -> StepReliabilityPolicy:
        return self.step_policies.get(step_name, self.default_policy)

    @staticmethod
    def _parse_policy(raw: Mapping[str, Any] | None) -> StepReliabilityPolicy:
        if not raw:
            return StepReliabilityPolicy()
        timeout = raw.get("timeout_seconds")
        retries = raw.get("max_attempts") or raw.get("retries") or raw.get("max_retries")
        timeout_value: float | None
        if timeout is None:
            timeout_value = None
        else:
            try:
                timeout_value = float(timeout)
            except (TypeError, ValueError):
                timeout_value = None
        attempts = 1
        if retries not in (None, ""):
            if isinstance(retries, (int, float, str)):
                try:
                    attempts = max(1, int(retries))
                except (TypeError, ValueError):
                    attempts = 1
            else:
                attempts = 1
        return StepReliabilityPolicy(timeout_seconds=timeout_value, max_attempts=attempts)

    @classmethod
    def from_meta(cls, meta: Mapping[str, Any] | None) -> "ReliabilityProfile":
        raw = (meta or {}).get("reliability") or {}
        default_raw = raw.get("default")
        steps_raw = raw.get("steps") or {}
        profile = cls(default_policy=cls._parse_policy(default_raw))
        if isinstance(steps_raw, Mapping):
            for step_name, policy_raw in steps_raw.items():
                if isinstance(policy_raw, Mapping):
                    profile.step_policies[step_name] = cls._parse_policy(policy_raw)
        return profile


@dataclass
class RunReliabilityState:
    run_id: str
    workspace_id: str | None = None
    bundle_artifact_id: str | None = None
    status: str = "pending"
    current_step: str | None = None
    attempt: int = 0
    retry_count: int = 0
    timeout_step: str | None = None
    timeout_seconds: float | None = None
    timeout_reason: str | None = None
    canceled: bool = False
    started_at: str = field(default_factory=_iso_now)
    ended_at: str | None = None
    errors: list[str] = field(default_factory=list)
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workspace_id": self.workspace_id,
            "bundle_artifact_id": self.bundle_artifact_id,
            "status": self.status,
            "current_step": self.current_step,
            "attempt": self.attempt,
            "retry_count": self.retry_count,
            "timeout_step": self.timeout_step,
            "timeout_seconds": self.timeout_seconds,
            "timeout_reason": self.timeout_reason,
            "canceled": self.canceled,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "errors": list(self.errors),
            "last_error": self.last_error,
        }


class RunReliabilityController:
    """Tracks reliability state for a controller cycle run."""

    def __init__(self, run_id: str, workspace_id: str | None = None, profile: ReliabilityProfile | None = None):
        self.state = RunReliabilityState(run_id=run_id, workspace_id=workspace_id)
        self._profile = profile or ReliabilityProfile()
        self._cancel_event = Event()
        self._lock = Lock()

    @property
    def profile(self) -> ReliabilityProfile:
        return self._profile

    def set_profile(self, profile: ReliabilityProfile) -> None:
        self._profile = profile

    def mark_bundle(self, bundle_id: str) -> None:
        self.state.bundle_artifact_id = bundle_id

    def mark_started(self) -> None:
        self.state.status = "running"
        self.state.started_at = _iso_now()

    def mark_attempt(self, step: str, attempt: int) -> None:
        with self._lock:
            self.state.current_step = step
            self.state.attempt = attempt
            self.state.retry_count = max(self.state.retry_count, attempt - 1)
            self.state.status = "running"
            self.state.last_error = None
            self.state.timeout_step = None
            self.state.timeout_seconds = None
            self.state.timeout_reason = None

    def mark_timeout(self, step: str, attempt: int, timeout_seconds: float | None, reason: str) -> None:
        with self._lock:
            self.state.timeout_step = step
            self.state.timeout_seconds = timeout_seconds
            self.state.timeout_reason = reason
            self.state.last_error = reason
            self.state.retry_count = max(self.state.retry_count, attempt)

    def mark_cancel_requested(self) -> None:
        with self._lock:
            self.state.canceled = True
            self.state.status = "cancelling"

    def mark_finished(self, success: bool, errors: Iterable[str] | None = None) -> None:
        with self._lock:
            if not success and self.state.canceled:
                self.state.status = "cancelled"
            else:
                self.state.status = "completed" if success else "failed"
            self.state.ended_at = _iso_now()
            if errors:
                self.state.errors = list(errors)
                self.state.last_error = self.state.errors[-1]

    def mark_failed(self, message: str) -> None:
        with self._lock:
            self.state.status = "failed"
            self.state.last_error = message
            if message not in self.state.errors:
                self.state.errors.append(message)

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def request_cancel(self) -> None:
        self._cancel_event.set()
        self.mark_cancel_requested()

    def ensure_not_cancelled(self) -> None:
        if self.is_cancelled():
            raise RunCancelledError("run cancelled")

    def to_dict(self) -> dict[str, Any]:
        return self.state.to_dict()


class RunRegistryEntry:
    def __init__(self, controller: RunReliabilityController, workspace_id: str | None):
        self.controller = controller
        self.workspace_id = workspace_id
        self.created_at = _iso_now()


_RUN_REGISTRY: Dict[str, RunRegistryEntry] = {}
_REGISTRY_LOCK = Lock()


def register_run(run_id: str, controller: RunReliabilityController, workspace_id: str | None = None) -> None:
    with _REGISTRY_LOCK:
        _RUN_REGISTRY[run_id] = RunRegistryEntry(controller=controller, workspace_id=workspace_id)


def get_run_entry(run_id: str) -> RunRegistryEntry | None:
    with _REGISTRY_LOCK:
        return _RUN_REGISTRY.get(run_id)


def list_runs(workspace_id: str | None = None) -> list[RunReliabilityState]:
    with _REGISTRY_LOCK:
        entries = list(_RUN_REGISTRY.values())
    if workspace_id is None:
        return [entry.controller.state for entry in entries]
    return [entry.controller.state for entry in entries if entry.workspace_id == workspace_id]


def cancel_run(run_id: str) -> RunReliabilityState | None:
    entry = get_run_entry(run_id)
    if entry is None:
        return None
    entry.controller.request_cancel()
    return entry.controller.state


def clear_run_registry() -> None:
    with _REGISTRY_LOCK:
        _RUN_REGISTRY.clear()


def run_with_timeout(func: Callable[[], Any], timeout: float | None) -> Any:
    if timeout is None or timeout <= 0:
        return func()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise StepTimeoutError(f"timed out after {timeout} seconds") from exc
