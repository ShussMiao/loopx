from __future__ import annotations

import json
from pathlib import Path

import pytest

from loopx.state_migration import migrate_legacy_state, render_state_migration_markdown


OLD_GOAL_ID = "legacy-goal"
NEW_GOAL_ID = "migrated-goal"
OLD_STORE_IDENTITY = "file:11111111111111111111111111111111"


def _migration_fixture(tmp_path: Path) -> dict[str, Path]:
    legacy_runtime = tmp_path / "legacy-runtime"
    target_runtime = tmp_path / "target-runtime"
    source_repo = tmp_path / "legacy-repo"
    target_repo = tmp_path / "target-repo"
    source_repo.mkdir()
    target_repo.mkdir()

    source_state = source_repo / "ACTIVE_GOAL_STATE.md"
    source_state.write_text(
        "---\n"
        f"goal_id: {OLD_GOAL_ID}\n"
        "handoff_mode: soft_claim\n"
        "updated_at: 2026-09-02T00:00:00+10:00\n"
        "---\n\n"
        "## Agent Todo\n\n"
        "- [ ] Preserve the new local authority only.\n",
        encoding="utf-8",
    )

    legacy_registry = tmp_path / "legacy-registry.json"
    legacy_registry.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "common_runtime_root": str(legacy_runtime),
                "goals": [
                    {
                        "id": OLD_GOAL_ID,
                        "status": "active",
                        "repo": str(source_repo),
                        "state_file": source_state.name,
                        "coordination": {
                            "agent_model": "peer_v1",
                            "registered_agents": ["agent-a", "agent-b"],
                            "authority_shadow": {
                                "schema_version": (
                                    "loopx_local_authority_shadow_config_v0"
                                ),
                                "mode": "file_one_way",
                            },
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    source_goal_runtime = legacy_runtime / "goals" / OLD_GOAL_ID
    (source_goal_runtime / "task-leases").mkdir(parents=True)
    (source_goal_runtime / "task-leases" / "safe-local.json").write_text(
        json.dumps(
            {
                "goal_id": OLD_GOAL_ID,
                "todo_id": "safe-local",
                "owner": "agent-a",
                "version": 1,
                "lease_epoch": 1,
                "status": "released",
            }
        ),
        encoding="utf-8",
    )
    source_shadow_store = (
        legacy_runtime / "authority-shadow" / "file" / OLD_GOAL_ID
    )
    source_shadow_store.mkdir(parents=True)
    (source_shadow_store / "store-identity").write_text(
        OLD_STORE_IDENTITY,
        encoding="utf-8",
    )
    (source_shadow_store / "authority-store-legacy.json").write_text(
        json.dumps(
            {
                "goal_id": OLD_GOAL_ID,
                "store_identity": OLD_STORE_IDENTITY,
                "provider_revision": "file:99:legacy-lineage",
                "cursor": "99",
                "private_provider_byte": "must-never-migrate",
                "source_path": str(source_repo),
            }
        ),
        encoding="utf-8",
    )

    return {
        "legacy_registry": legacy_registry,
        "target_registry": tmp_path / "target-registry.json",
        "legacy_runtime": legacy_runtime,
        "target_runtime": target_runtime,
        "source_repo": source_repo,
        "target_repo": target_repo,
    }


def _migrate(paths: dict[str, Path], *, execute: bool) -> dict[str, object]:
    return migrate_legacy_state(
        legacy_registry_path=paths["legacy_registry"],
        target_registry_path=paths["target_registry"],
        legacy_runtime_root=paths["legacy_runtime"],
        target_runtime_root=paths["target_runtime"],
        goal_ids=[OLD_GOAL_ID],
        goal_id_map={OLD_GOAL_ID: NEW_GOAL_ID},
        path_map={str(paths["source_repo"]): str(paths["target_repo"])},
        copy_active_state=True,
        copy_runtime=True,
        execute=execute,
    )


@pytest.mark.parametrize("execute", [False, True])
def test_migration_preserves_old_store_without_reseeding_retired_lineage(tmp_path: Path, execute: bool) -> None:
    paths = _migration_fixture(tmp_path)
    old_dir = paths["legacy_runtime"] / "authority-shadow" / "file" / OLD_GOAL_ID
    before = {p.name: p.read_bytes() for p in old_dir.iterdir()}
    result = _migrate(paths, execute=execute)
    assert result["ok"] is True
    assert result["authority_shadow_seeds"] == [{
        "schema_version": "loopx_state_migration_shadow_seed_evidence_v0",
        "goal_id": NEW_GOAL_ID, "attempted": False, "outcome": "retired",
        "reason_code": "local_authority_shadow_retired"}]
    assert not (paths["target_runtime"] / "authority-shadow").exists()
    assert {p.name: p.read_bytes() for p in old_dir.iterdir()} == before
    assert "retired" in render_state_migration_markdown(result)
    if execute:
        target = json.loads(paths["target_registry"].read_text())["goals"][0]
        assert target["id"] == NEW_GOAL_ID
        assert "runtime_shadow" not in target["coordination"]
        lease = paths["target_runtime"] / "goals" / NEW_GOAL_ID / "task-leases" / "safe-local.json"
        assert json.loads(lease.read_text())["goal_id"] == NEW_GOAL_ID
    else:
        assert not paths["target_registry"].exists()
