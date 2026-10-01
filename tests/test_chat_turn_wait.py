from __future__ import annotations

import threading
from unittest.mock import Mock

from loopx.chat_runtime import ChatRuntimeController


def _runtime() -> ChatRuntimeController:
    runtime = ChatRuntimeController.__new__(ChatRuntimeController)
    runtime.store = Mock()  # type: ignore[assignment]
    runtime.lock = threading.RLock()
    runtime.turn_done_events = {}
    return runtime


def test_wait_for_turn_uses_managed_completion_event() -> None:
    runtime = _runtime()
    runtime.store.load_turn.side_effect = [{"status": "running"}, {"status": "completed"}]
    completion = Mock()
    runtime.turn_done_events[("session", "turn")] = completion  # type: ignore[assignment]

    turn = runtime.wait_for_turn(session_id="session", turn_id="turn", timeout_sec=0.1)

    assert turn["status"] == "completed"
    completion.wait.assert_called_once()
    assert runtime.store.load_turn.call_count == 2


def test_wait_for_turn_performs_final_fallback_read_at_deadline() -> None:
    runtime = _runtime()
    runtime.store.load_turn.side_effect = [{"status": "running"}, {"status": "completed"}]

    turn = runtime.wait_for_turn(session_id="session", turn_id="turn", timeout_sec=0.001)

    assert turn["status"] == "completed"
    assert runtime.store.load_turn.call_count == 2
