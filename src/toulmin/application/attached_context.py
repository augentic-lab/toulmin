"""Retry an unsent startup context while the researcher is attached to native UI."""

import threading
import time
from types import TracebackType

from toulmin.adapters.aoe import AoEClient, AoEError
from toulmin.application.aoe import AoEWorkspace, WorkspaceView

TIMEOUT_SECONDS = 180.0
POLL_SECONDS = 1.0


class AttachedContext:
    """One bounded in-process watcher; no daemon, terminal or implicit resend."""

    def __init__(self, workspace: AoEWorkspace, client: AoEClient, view: WorkspaceView):
        self.workspace, self.client, self.initial = workspace, client, view
        self.latest: WorkspaceView | None = None
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "AttachedContext":
        binding = self.initial.binding
        if binding and binding.context and binding.session_id and binding.delivery == "prepared":
            self.thread = threading.Thread(
                target=self._watch, name="toulmin-startup-context", daemon=True
            )
            self.thread.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop.set()
        if self.thread is not None:
            # A bounded readiness observation may still be in flight. It checks stop
            # before refresh, so detaching cannot start a later context submission.
            self.thread.join(timeout=1.0)

    def _watch(self) -> None:
        expected = self.initial.binding
        assert expected is not None and expected.session_id is not None
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while not self.stop.wait(POLL_SECONDS):
            if time.monotonic() >= deadline:
                return
            try:
                binding = self.workspace.bound_session()
                if binding is None or (
                    binding.session_id != expected.session_id
                    or binding.profile != expected.profile
                    or binding.token != expected.token
                    or binding.delivery != "prepared"
                ):
                    return
                ready, _ = self.client.ready(expected.session_id)
                if self.stop.is_set() or time.monotonic() >= deadline:
                    return
                if not ready:
                    continue
                # Revalidate under the service lock: never refresh a replacement
                # binding or resend another operation's submitted/uncertain message.
                self.latest = self.workspace.refresh(
                    expected=expected,
                    cancelled=lambda: self.stop.is_set() or time.monotonic() >= deadline,
                )
                current = self.latest.binding
                if (
                    current is not None
                    and current.delivery == "prepared"
                    and current.session_id == expected.session_id
                    and current.profile == expected.profile
                    and not self.latest.research.errors
                    and not self.latest.context_status.startswith("invalid")
                ):
                    # The native UI can change between readiness checks. Only our
                    # own revalidated refresh may advance the watched context token.
                    expected = current
                    continue
                return
            except (AoEError, OSError, ValueError):
                # Keep the binding's existing diagnostics and explicit recovery path.
                return
