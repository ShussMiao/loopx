"""Full source transfer through public qualification and reviewed cutover.

Large notes are semantic source fields, not discarded prose or padding outside
Todos. Every CLI call runs in a fresh process against disposable real storage.
"""
import json

import pytest

from test_runtime_shadow_bounded_e2e import cli, enable, workspace
from loopx.control_plane.coordination.runtime_shadow import build_runtime_shadow_source_snapshot
from loopx.control_plane.effect_runtime import MAX_REQUEST_BYTES
from loopx.control_plane.todos.contract import format_todo_metadata_line

pytestmark = pytest.mark.stage2c_e2e


def test_large_complete_source_can_qualify_promote_and_read_back(tmp_path):
    registry, runtime, state = workspace(tmp_path)
    note = "完整🙂" * 1600
    blocks = [f"- [ ] Retained work {index}\n  " + format_todo_metadata_line(
        todo_id=f"todo_{index:03}", role="agent", status="open",
        task_class="advancement_task", note=note,
    ) for index in range(160)]
    state.write_text(state.read_text() + "\n".join(blocks) + "\n", encoding="utf-8")
    goal = enable(registry)
    projection, _ = build_runtime_shadow_source_snapshot(
        goal=goal, runtime_root=runtime, state_path=state, registry_path=registry)
    assert len(json.dumps(projection, ensure_ascii=False).encode()) > MAX_REQUEST_BYTES
    assert len(projection["todos"]) == 160
    assert all(todo["note"] == note for todo in projection["todos"])

    boot = cli(registry, runtime, "coordination-shadow", "bootstrap", "--goal-id", "goal-a", "--execute")
    assert boot["bootstrap"]["status"] == "applied"
    added = cli(registry, runtime, "todo", "add", "--goal-id", "goal-a", "--role", "agent", "--text", "Captured after full bootstrap")
    assert added["coordination_runtime_shadow"]["source_transaction_correlated"] is True
    inspected = cli(registry, runtime, "coordination-shadow", "inspect", "--goal-id", "goal-a")
    assert inspected["inspection"]["status"] == "matched"
    qualified = cli(registry, runtime, "coordination-shadow", "qualify", "--goal-id", "goal-a",
                    "--minimum-operations", "1", "--require-event-kind", "todo_add")
    assert qualified["qualification"]["qualified"] is True
    assert qualified["qualification"]["sustained_parity_verified"] is False
    common = ("coordination-shadow", "promote", "--goal-id", "goal-a",
              "--minimum-operations", "1", "--require-event-kind", "todo_add")
    preview = cli(registry, runtime, *common)
    assert preview["promotion"]["status"] == "preview_ready"
    assert not (runtime / "authority" / "file-v0").exists()
    applied = cli(registry, runtime, *common, "--execute")
    assert applied["promotion"]["status"] == "applied"
    assert applied["promotion"]["legacy_writer_fenced"] is True
    read = cli(registry, runtime, "todo", "list", "--goal-id", "goal-a", "--role", "agent")
    assert len(read["todos"]) == 161
    retained = [row for row in read["todos"] if row["todo_id"] != added["todo_id"]]
    assert {row["todo_id"] for row in retained} == {f"todo_{i:03}" for i in range(160)}
    assert all(row["note"] == note for row in retained)
