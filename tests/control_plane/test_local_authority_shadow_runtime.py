from __future__ import annotations

import json
from pathlib import Path

import pytest

from loopx.control_plane.work_items.task_lease import (
    acquire_task_lease,
    release_task_lease,
    renew_task_lease,
)
from loopx.todos import (
    add_goal_todo,
)


GOAL_ID = "goal-shadow"
AGENT_A = "agent-a"
AGENT_B = "agent-b"


def _fixture(tmp_path: Path, *, enabled: bool) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = repo / "ACTIVE_GOAL_STATE.md"
    state.write_text(
        "---\n"
        f"goal_id: {GOAL_ID}\n"
        "handoff_mode: hard_lease\n"
        "updated_at: 2026-09-02T00:00:00+00:00\n"
        "---\n\n"
        "## Agent Todo\n\n",
        encoding="utf-8",
    )
    runtime_root = tmp_path / "runtime"
    coordination: dict[str, object] = {
        "agent_model": "peer_v1",
        "registered_agents": [AGENT_A, AGENT_B],
    }
    if enabled:
        coordination["authority_shadow"] = {
            "schema_version": "loopx_local_authority_shadow_config_v0",
            "mode": "file_one_way",
        }
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "common_runtime_root": str(runtime_root),
                "goals": [
                    {
                        "id": GOAL_ID,
                        "domain": "harness_self_improvement",
                        "status": "active",
                        "repo": str(repo),
                        "state_file": state.name,
                        "adapter": {"kind": "harness_self_improvement"},
                        "coordination": coordination,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return registry, state, runtime_root


def _add(registry: Path) -> dict:
    return add_goal_todo(
        registry_path=registry,
        goal_id=GOAL_ID,
        role="agent",
        text="Continue primary work with a retained observation setting.",
        task_class="advancement_task",
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_retired_and_absent_settings_leave_public_writers_on_primary_only(tmp_path: Path, enabled: bool) -> None:
    registry, state, runtime = _fixture(tmp_path, enabled=enabled)
    retained = runtime / "authority-shadow" / "file" / GOAL_ID / "historical.json"
    if enabled:
        retained.parent.mkdir(parents=True)
        retained.write_bytes(b'{"historical":true}\n')
    before = retained.read_bytes() if enabled else None
    added = _add(registry)
    todo_id = added["todo_id"]
    acquired = acquire_task_lease(registry_path=registry, runtime_root=runtime, goal_id=GOAL_ID,
        todo_id=todo_id, owner=AGENT_A, idempotency_key="retired-writer", ttl_seconds=120)
    renewed = renew_task_lease(registry_path=registry, runtime_root=runtime, goal_id=GOAL_ID,
        todo_id=todo_id, owner=AGENT_A, idempotency_key="retired-writer",
        expected_version=acquired["lease"]["version"], ttl_seconds=180)
    released = release_task_lease(registry_path=registry, runtime_root=runtime, goal_id=GOAL_ID,
        todo_id=todo_id, owner=AGENT_A, idempotency_key="retired-writer",
        expected_version=renewed["lease"]["version"])
    for result in (added, acquired, renewed, released):
        assert result["ok"] is True
        assert "authority_shadow" not in result
    assert todo_id in state.read_text()
    assert not (runtime / "authority-shadow" / "outbox").exists()
    assert not (runtime / "authority-shadow" / "file-v0").exists()
    if enabled:
        assert retained.read_bytes() == before
        assert list(retained.parent.iterdir()) == [retained]
    else:
        assert not (runtime / "authority-shadow").exists()
