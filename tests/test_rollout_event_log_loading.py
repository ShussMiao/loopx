from __future__ import annotations

import json
from pathlib import Path

import pytest

import loopx.rollout_event_log as rollout_event_log
from loopx.rollout_event_log import (
    append_rollout_event,
    append_rollout_event_once,
    build_rollout_event,
    iter_rollout_events,
    load_rollout_events,
)


def test_limited_rollout_event_load_keeps_only_a_bounded_window(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class TrackedEvent(dict[str, int]):
        alive = 0
        peak = 0

        def __init__(self, index: int) -> None:
            super().__init__(index=index)
            type(self).alive += 1
            type(self).peak = max(type(self).peak, type(self).alive)

        def __del__(self) -> None:
            type(self).alive -= 1

    monkeypatch.setattr(
        rollout_event_log,
        "iter_rollout_events",
        lambda _path: (TrackedEvent(index) for index in range(100)),
    )

    events = rollout_event_log.load_rollout_events(tmp_path / "unused", limit=3)

    assert [event["index"] for event in events] == [97, 98, 99]
    assert TrackedEvent.peak <= 4


@pytest.mark.parametrize("idempotent", [False, True])
@pytest.mark.parametrize(
    "torn_record",
    [
        b'{"schema_version":"loopx_rollout_event_v0"',
        b'{"summary":"' + "雪".encode()[:2],
    ],
    ids=["ascii", "mid-utf8"],
)
def test_append_starts_a_new_row_after_a_torn_final_record(
    tmp_path: Path,
    idempotent: bool,
    torn_record: bytes,
) -> None:
    log_path = tmp_path / "rollout-event-log.jsonl"
    existing = build_rollout_event(
        goal_id="goal-a",
        event_kind="quota_should_run",
        agent_id="agent-a",
        run_id="turn-before",
        status="run",
        recorded_at="2026-09-22T00:00:00Z",
    )
    log_path.write_bytes(
        json.dumps(existing, sort_keys=True).encode("utf-8")
        + b"\n"
        + torn_record
    )
    event = build_rollout_event(
        goal_id="goal-a",
        event_kind="quota_should_run",
        agent_id="agent-a",
        run_id="turn-a",
        status="run",
        recorded_at="2026-09-23T00:00:00Z",
    )

    if idempotent:
        written, appended = append_rollout_event_once(
            log_path,
            event,
            identity_fields=("goal_id", "event_kind", "agent_id", "run_id"),
        )
        assert appended is True
    else:
        written = append_rollout_event(log_path, event)

    assert torn_record + b"\n" in log_path.read_bytes()
    assert load_rollout_events(log_path) == [existing, written]


@pytest.mark.parametrize("idempotent", [False, True])
def test_append_replays_an_event_before_a_mid_utf8_torn_record(
    tmp_path: Path,
    idempotent: bool,
) -> None:
    log_path = tmp_path / "rollout-event-log.jsonl"
    event = build_rollout_event(
        goal_id="goal-a",
        event_kind="quota_should_run",
        agent_id="agent-a",
        run_id="turn-a",
        status="run",
        recorded_at="2026-09-23T00:00:00Z",
    )
    torn_record = b'{"summary":"' + "雪".encode()[:2]
    original = (
        json.dumps(event, sort_keys=True, ensure_ascii=False).encode("utf-8")
        + b"\n"
        + torn_record
    )
    log_path.write_bytes(original)

    if idempotent:
        replayed, appended = append_rollout_event_once(
            log_path,
            event,
            identity_fields=("goal_id", "event_kind", "agent_id", "run_id"),
        )
        assert appended is False
    else:
        replayed = append_rollout_event(log_path, event)

    assert replayed == event
    assert log_path.read_bytes() == original


def test_strict_read_reports_a_mid_utf8_torn_record(tmp_path: Path) -> None:
    log_path = tmp_path / "rollout-event-log.jsonl"
    event = build_rollout_event(
        goal_id="goal-a",
        event_kind="quota_should_run",
        recorded_at="2026-09-23T00:00:00Z",
    )
    log_path.write_bytes(
        json.dumps(event, sort_keys=True).encode("utf-8")
        + b"\n"
        + b'{"summary":"'
        + "雪".encode()[:2]
    )

    with pytest.raises(
        ValueError,
        match="rollout event log line 2 must contain valid UTF-8",
    ):
        list(iter_rollout_events(log_path, strict=True))
