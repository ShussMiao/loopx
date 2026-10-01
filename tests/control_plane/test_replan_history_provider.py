"""Real canonical stores feed the public quota consumer, including retry history."""
from copy import deepcopy
import json

import pytest

from canonical_authority_fixture import initialize_canonical_authority, isolate_sqlite_runtime
from test_canonical_frontier_revision import _fixture
from test_goal_amendment_proposal import _write_fixture, _stall_runs, _ack_run, GOAL_ID
from loopx.control_plane.testing.canary_harness import run_json_cli_result
from loopx.status import active_state_todo_fields, autonomous_replan_obligation_from_runs


@pytest.mark.parametrize("provider", ["file", "sqlite"])
def test_complex_provider_snapshot_replan_and_quota_readback(tmp_path, monkeypatch, provider):
    isolate_sqlite_runtime(tmp_path, monkeypatch)
    paths = _write_fixture(tmp_path, runs=[])
    projection = _fixture()
    initialize_canonical_authority(paths["runtime"], GOAL_ID, projection,
                                   state_path=paths["state_file"], provider=provider)
    # The display is absent: the production reader must use persisted authority.
    paths["state_file"].unlink()
    goal = json.loads(paths["registry"].read_text())["goals"][0]
    summary = active_state_todo_fields(goal, runtime_root=paths["runtime"])["agent_todos"]
    history = list(reversed(_stall_runs()))
    current = autonomous_replan_obligation_from_runs(history, agent_todos=summary, agent_id="agent-a")
    assert current["triggers"][0]["kind"] == "typed_progress_repeat"
    assert autonomous_replan_obligation_from_runs([history[0]] * 8,
        agent_todos=summary, agent_id="agent-a") is None
    ack = _ack_run(current["obligation_id"])
    assert autonomous_replan_obligation_from_runs([ack, *history],
        agent_todos=summary, agent_id="agent-a") is None
    peer_ack = {**deepcopy(ack), "agent_id": "agent-b"}
    assert autonomous_replan_obligation_from_runs([peer_ack, *history],
        agent_todos=summary, agent_id="agent-a") == current
    index = paths["runtime"] / "goals" / GOAL_ID / "runs" / "index.jsonl"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("".join(json.dumps(row) + "\n" for row in reversed(history)))
    code, result = run_json_cli_result("quota", "should-run", "--goal-id", GOAL_ID,
        "--agent-id", "agent-a", registry_path=paths["registry"])
    assert code == 0, result
    assert "typed_progress_repeat" in json.dumps(result)
    assert active_state_todo_fields(goal, runtime_root=paths["runtime"])["agent_todos"] == summary
    assert not paths["state_file"].exists()
