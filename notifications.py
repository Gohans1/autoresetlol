"""Background notifications through Hermes's configured Discord sender."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import queue
import subprocess
import threading
import time
from typing import Callable, Optional

from logger import logger

HERMES_SEND_COMMAND = ("hermes", "send", "--to", "discord", "--quiet")
_SEND_TIMEOUT_SECONDS = 20
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY_SECONDS = 1.0
_DEFAULT_QUEUE_SIZE = 32
_MAX_DEDUPE_KEYS = 4096


@dataclass(frozen=True)
class Notification:
    """One user-facing event waiting for delivery."""

    event: str
    message: str
    dedupe_key: Optional[str] = None
    event_generation: int = 0


def _terminate_process(process: subprocess.Popen) -> None:
    """Stop a Hermes child process without leaking it during app shutdown."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.communicate(timeout=0.2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.communicate(timeout=0.2)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _run_hermes_send(
    message: str,
    cancel_event: Optional[threading.Event] = None,
) -> bool:
    """Send one message through Hermes without exposing its command output."""
    popen_kwargs = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    process = None
    try:
        process = subprocess.Popen(
            HERMES_SEND_COMMAND,
            **popen_kwargs,
        )
        deadline = time.monotonic() + _SEND_TIMEOUT_SECONDS
        pending_input: Optional[str] = message
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _terminate_process(process)
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_process(process)
                return False
            try:
                process.communicate(
                    input=pending_input,
                    timeout=min(0.2, remaining),
                )
                return process.returncode == 0
            except subprocess.TimeoutExpired:
                pending_input = None
    except (FileNotFoundError, OSError) as error:
        logger.debug("Hermes Discord send unavailable: %s", error)
        return False
    finally:
        if process is not None and process.poll() is None:
            _terminate_process(process)


class HermesNotifier:
    """Queue best-effort notifications without blocking the LCU watcher."""

    def __init__(
        self,
        runner: Optional[Callable[[str], bool]] = None,
        *,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_delay: float = _DEFAULT_RETRY_DELAY_SECONDS,
        queue_size: int = _DEFAULT_QUEUE_SIZE,
    ) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be positive")
        if retry_delay < 0:
            raise ValueError("retry_delay must not be negative")
        if queue_size < 1:
            raise ValueError("queue_size must be positive")

        self._runner = runner
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._queue: queue.Queue[Notification] = queue.Queue(
            maxsize=queue_size
        )
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._closed = False
        self._dedupe_keys: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._enabled_events: dict[str, bool] = {}
        self._event_generations: dict[str, int] = {}
        self._thread = threading.Thread(
            target=self._run,
            name="HermesNotifier",
            daemon=True,
        )
        if runner is None:
            self._runner = lambda message: _run_hermes_send(
                message,
                cancel_event=self._stop,
            )
        self._thread.start()

    def notify(
        self,
        event: str,
        message: str,
        dedupe_key: Optional[str] = None,
    ) -> bool:
        """Queue one event; return False when it is rejected or duplicated."""
        event = str(event).strip()
        message = str(message).strip()
        key = str(dedupe_key).strip() if dedupe_key else ""
        if not event or not message:
            return False

        with self._lock:
            if self._closed or not self._enabled_events.get(event, True):
                return False
            dedupe_token = (event, key)
            if key and dedupe_token in self._dedupe_keys:
                return False
            if key:
                self._dedupe_keys[dedupe_token] = None
                self._dedupe_keys.move_to_end(dedupe_token)
                if len(self._dedupe_keys) > _MAX_DEDUPE_KEYS:
                    self._dedupe_keys.popitem(last=False)
            item = Notification(
                event,
                message,
                key or None,
                self._event_generations.get(event, 0),
            )
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                if key:
                    self._dedupe_keys.pop(dedupe_token, None)
                logger.warning("Discord notification queue is full: %s", event)
                return False
        return True

    def set_event_enabled(self, event: str, enabled: bool) -> None:
        """Enable one event type and invalidate queued work when disabling it."""
        event = str(event).strip()
        if not event:
            return
        with self._lock:
            self._enabled_events[event] = bool(enabled)
            if not enabled:
                self._event_generations[event] = (
                    self._event_generations.get(event, 0) + 1
                )
                self._dedupe_keys = OrderedDict(
                    (token, None)
                    for token in self._dedupe_keys
                    if token[0] != event
                )

    def close(self, timeout: float = 1.0) -> None:
        """Stop accepting events and give the worker a short shutdown window."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=max(0.0, timeout))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self._deliver(item)
            finally:
                self._queue.task_done()

    def _deliver(self, item: Notification) -> None:
        for attempt in range(self._max_retries):
            if self._stop.is_set() or not self._event_allowed(item):
                return
            try:
                if self._runner(item.message):
                    return
            except Exception:
                logger.exception(
                    "Discord notification runner crashed for event=%s",
                    item.event,
                )
            if self._stop.is_set():
                return

            if attempt + 1 < self._max_retries and self._retry_delay:
                if self._stop.wait(self._retry_delay * (2**attempt)):
                    return

        if self._stop.is_set():
            return
        logger.warning(
            "Discord notification failed after %d attempts: event=%s",
            self._max_retries,
            item.event,
        )

    def _event_allowed(self, item: Notification) -> bool:
        with self._lock:
            return (
                self._enabled_events.get(item.event, True)
                and self._event_generations.get(item.event, 0)
                == item.event_generation
            )
