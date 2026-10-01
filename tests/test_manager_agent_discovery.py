"""Discovery searches the allowed inventory; a delivery list is not that scope."""

import json
import subprocess
import sys

import pytest

from loopx.capabilities.manager_context.inspection import ManagerInspection, TOOL_NAME


def setup(tmp_path, *, owner=True, scope=None, valid=lambda: True):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"goals": [
        {"id": "research", "coordination": {
            "registered_agents": [f"worker-{i:02}" for i in range(35)],
            "agent_profiles": {"worker-34": {"profile_role": "reviewer", "scope_summary": "Independent PR review"}},
        }},
        {"id": "history", "activation_state": "stopped", "registered_agents": ["old-worker"]},
        {"id": "private", "registered_agents": ["hidden-worker"]},
    ]}))
    records = []
    inspector = ManagerInspection(
        context={"scope": "owner_global" if owner else "external_goal_scope", "goals": []},
        registry_path=registry, runtime_root=tmp_path, owner_scope=owner,
        scope_valid=valid, record=records.append,
        discovery_scope=scope or (lambda: None if owner else ["research"]),
        delegation_authority=lambda: {"mode": "context_only", "targets": [{"goal_id": "research", "agent_id": "worker-00"}]},
    )
    return registry, inspector, records


def test_full_inventory_search_is_independent_of_initial_portfolio_and_delivery(tmp_path):
    _, reader, records = setup(tmp_path)
    result = reader.read(TOOL_NAME, {"view": "agents", "query": "PR REVIEW"})
    assert result["ok"] and result["matched"] == 1
    row = result["rows"][0]
    assert row["agent_id"] == "worker-34"  # beyond both historical 8/24 row caps
    assert row["context_delivery"] == "not_granted"
    assert row["execution_readiness"] == "not_checked"
    assert len(records) == 1
    offset, found, revisions = 0, [], set()
    while offset is not None:
        page = reader.read(TOOL_NAME, {"view": "agents", "goal_id": "research", "offset": offset})
        found.extend(r["agent_id"] for r in page["rows"])
        revisions.add(page["source"]["source_revision"])
        offset = page["next_offset"]
    assert found == [f"worker-{i:02}" for i in range(35)]
    assert len(revisions) == 1


def test_audience_scope_is_distinct_from_sender_delivery_and_cannot_leak(tmp_path):
    _, reader, _ = setup(tmp_path, owner=False)
    all_rows = reader.read(TOOL_NAME, {"view": "agents"})
    assert all_rows["matched"] == 35
    assert all_rows["rows"][0]["context_delivery"] == "allowed"
    assert reader.read(TOOL_NAME, {"view": "agents", "query": "hidden"})["matched"] == 0
    assert reader.read(TOOL_NAME, {"view": "agents", "goal_id": "private"})["error"] == "goal_outside_available_scope"


def test_stopped_is_historical_not_a_delivery_target(tmp_path):
    _, reader, _ = setup(tmp_path)
    assert reader.read(TOOL_NAME, {"view": "agents", "query": "old-worker"})["matched"] == 0
    result = reader.read(TOOL_NAME, {"view": "agents", "query": "old-worker", "include_stopped": True})
    assert result["rows"][0]["context_delivery"] == "goal_stopped"


def test_no_match_does_not_hide_unreadable_inventory(tmp_path):
    registry, reader, _ = setup(tmp_path)
    registry.write_text("{")
    result = reader.read(TOOL_NAME, {"view": "agents"})
    assert not result["ok"] and result["unknown"] and result["matched"] is None
    assert result["error"] == "agent_inventory_unavailable"


def test_revocation_during_discovery_discards_evidence(tmp_path):
    checks = iter([True, False])
    _, reader, records = setup(tmp_path, valid=lambda: next(checks))
    assert reader.read(TOOL_NAME, {"view": "agents"}) == {"ok": False, "error": "authorization_changed"}
    assert not records


def test_null_external_scope_never_becomes_owner_scope(tmp_path):
    _, reader, records = setup(tmp_path, owner=False, scope=lambda: None)
    assert reader.read(TOOL_NAME, {"view": "agents"})["error"] == "authorization_changed"
    assert not records


def test_goal_chat_cannot_inherit_owner_global_discovery(tmp_path):
    _, reader, _ = setup(tmp_path, scope=lambda: ["research"])
    reader.context["scope"] = "owner_goal"
    assert reader.read(TOOL_NAME, {"view": "agents", "query": "hidden"})["matched"] == 0


@pytest.mark.parametrize("arguments", [
    {"view": "portfolio", "query": "review"},
    {"view": "agents", "query": False},
    {"view": "agents", "query": "x" * 201},
])
def test_invalid_search_never_reads_source(tmp_path, arguments):
    _, reader, records = setup(tmp_path)
    assert reader.read(TOOL_NAME, arguments)["error"] == "invalid_arguments"
    assert not records


def test_real_cli_export_reaches_owner_beyond_old_caps_without_a_live_provider(tmp_path):
    registry, _, _ = setup(tmp_path)
    result = subprocess.run([
        sys.executable, "-m", "loopx.cli", "--registry", str(registry),
        "--runtime-root", str(tmp_path / "runtime"), "--format", "json",
        "goal-portfolio", "--manager-view", "agents", "--query", "PR review",
        "--goal-id", "research",
    ], capture_output=True, text=True, check=True)
    page = json.loads(result.stdout)
    assert page["schema_version"] == "manager_evidence_page_v1"
    assert [r["agent_id"] for r in page["rows"]] == ["worker-34"]
    assert page["rows"][0]["context_delivery"] == "not_checked"
    assert not (tmp_path / "runtime" / "chat").exists()
