"""Real CLI upgrade from a retired setting to an explicit capture lineage."""
from __future__ import annotations

import json
from pathlib import Path

from tests.control_plane.shadow_e2e_fixture import workspace


def test_retired_setting_cannot_enable_capture_or_satisfy_bootstrap(tmp_path: Path) -> None:
    ws = workspace(tmp_path, bootstrap=False)
    data = json.loads(ws.registry.read_text())
    config = data["goals"][0]["coordination"]
    config.pop("runtime_shadow")
    config["authority_shadow"] = {"schema_version": "loopx_local_authority_shadow_config_v0", "mode": "file_one_way"}
    ws.registry.write_text(json.dumps(data))
    original = ws.registry.read_bytes()
    rejected = ws.cli("configure-goal", "--local-authority-shadow-file", "--execute", success=False)
    assert rejected["ok"] is False
    assert "local_authority_shadow_retired" in rejected["error"]
    assert ws.registry.read_bytes() == original
    initial = ws.add("Continue work with a retained retired configuration.")
    assert "authority_shadow" not in initial
    status = ws.cli("authority-shadow", "status")
    assert status["config"]["status"] == "retired"
    assert status["config"]["enabled"] is False
    assert status["candidate"]["status"] == "missing"
    assert status["management"]["status"] == "missing"
    drain = ws.drain()
    assert drain["config_enabled"] is False
    assert not (ws.runtime / "authority-shadow").exists()

    # Configuration is not a source transaction or an automatic bootstrap.
    ws.cli("configure-goal", "--clear-local-authority-shadow", "--coordination-runtime-shadow-file", "--execute")
    assert not (ws.runtime / "authority-shadow" / "file-v0").exists()
    boot = ws.cli("coordination-shadow", "bootstrap", "--execute")
    assert boot["bootstrap"]["status"] == "applied"
    added = ws.add("Capture the next transaction using the existing outbox.")
    assert added["coordination_runtime_shadow"]["outcome"] in {"delivered", "replayed"}
    assert "authority_shadow" not in added
    status = ws.cli("authority-shadow", "status")
    assert status["config"]["status"] == "disabled"
    assert status["management"]["status"] == "active"
    assert status["candidate"]["codec_agreement"] is True
    assert not (ws.runtime / "authority-shadow" / "file" / ws.goal).exists()


def test_clearing_old_setting_does_not_retire_an_active_capture(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    data = json.loads(ws.registry.read_text())
    data["goals"][0]["coordination"]["authority_shadow"] = {
        "schema_version": "loopx_local_authority_shadow_config_v0", "mode": "file_one_way"}
    ws.registry.write_text(json.dumps(data))
    before = ws.cli("authority-shadow", "status")["management"]
    ws.cli("configure-goal", "--clear-local-authority-shadow", "--execute")
    after = ws.cli("authority-shadow", "status")["management"]
    assert after == before
    # Existing process-loss recovery still owns the source transaction.
    crashed = ws.crash("before_marker", "todo", "add", "--role", "agent", "--text", "Recover captured source.")
    assert crashed is not None
    result = ws.drain()
    assert result["ok"] is True
    assert result["drained_count"] == 1
    assert ws.drain()["drained_count"] == 0
