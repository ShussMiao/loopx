"""Upgrade acceptance for the retired, post-commit observation lineage."""
from __future__ import annotations

from .authority_e2e_fixtures import build_goal_workspace, run_cli, unique_goal_id
from .authority_e2e_row_support import RowContext, RowOutcome, add_todo, expect, passed
from .authority_e2e_rows_stage2c2 import bootstrap_capture, delivered, goal_cli


def row_retired_observation_upgrade(context: RowContext) -> RowOutcome:
    workspace = build_goal_workspace(context.root, goal_id=unique_goal_id("retired-observer"),
                                     handoff_mode="hard_lease", shadow_enabled=True,
                                     runtime_root_binding="cli_override")
    original = workspace.registry_path.read_bytes()
    rejected = goal_cli(workspace, "configure-goal", "--local-authority-shadow-file", "--execute", check=False)
    expect(rejected.get("ok") is False and "local_authority_shadow_retired" in str(rejected.get("error")),
           "retired enable must fail with actionable context")
    expect(workspace.registry_path.read_bytes() == original, "rejection must not change configuration")
    added = add_todo(workspace, "Continue work before explicit capture upgrade.")
    expect("authority_shadow" not in added, "a retained setting cannot restore observation writes")
    status = goal_cli(workspace, "authority-shadow", "status")
    expect(status["config"]["status"] == "retired" and status["config"]["enabled"] is False,
           "status must disclose the inactive historical configuration")
    expect(not (workspace.runtime_root / "authority-shadow").exists(), "primary work must create no shadow lineage")
    run_cli(workspace, "configure-goal", "--goal-id", workspace.goal_id,
            "--clear-local-authority-shadow", "--coordination-runtime-shadow-file", "--execute")
    expect(not (workspace.runtime_root / "authority-shadow" / "file-v0").exists(),
           "configuration must not implicitly bootstrap a source lineage")
    bootstrap_capture(workspace)
    delivered(add_todo(workspace, "Capture a transaction after explicit bootstrap."), label="upgraded write")
    expect(not workspace.shadow_directory.exists(), "replacement capture must not recreate historical observation storage")
    return passed(retired_enable_rejected=True, implicit_capture=False, explicit_bootstrap=True)
