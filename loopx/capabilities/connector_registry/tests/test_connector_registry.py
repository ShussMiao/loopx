from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loopx.capabilities.connector_registry.core import (
    BUILTIN_CONNECTOR_CATALOG,
    list_connectors,
    load_connector_registry,
    rank_connectors,
    record_connector_use,
    register_connector,
    save_connector_registry,
)


def test_builtin_catalog_covers_layers(tmp_path: Path) -> None:
    layers = {c["layer"] for c in BUILTIN_CONNECTOR_CATALOG}
    assert layers == {"L0", "L1", "L2", "L3", "L4", "L5"}
    ids = [c["id"] for c in BUILTIN_CONNECTOR_CATALOG]
    assert len(ids) == len(set(ids))
    assert "cninfo-announcement" in ids
    assert "ark-web-search" in ids


def test_register_use_rank_persists(tmp_path: Path) -> None:
    path = tmp_path / "connector-registry.json"
    state = load_connector_registry(path)
    result = register_connector(state, "probe-connector", status="supported",
                                value_tier="P0", layer="L1", kind="announcement")
    state2 = {**state, "connectors": result["connectors"], "usage": result["usage_map"]}
    used = record_connector_use(state2, "probe-connector", ok=True, ms=120)
    state3 = {**state2, "connectors": used["connectors"], "usage": used["usage_map"]}
    save_connector_registry(state3, path)

    reloaded = load_connector_registry(path)
    entry = next(c for c in reloaded["connectors"] if c["id"] == "probe-connector")
    assert entry["status"] == "supported"
    assert reloaded["usage"]["probe-connector"]["count"] == 1
    assert reloaded["usage"]["probe-connector"]["ok"] == 1

    ranked = rank_connectors(reloaded)
    top = ranked[0]
    assert top["score"] > 0
    packet = list_connectors(reloaded)
    assert packet["summary"]["supported"] >= 1
    assert json.dumps(packet, ensure_ascii=False)


def test_builtin_connector_updates_survive_catalog_resync(tmp_path: Path) -> None:
    path = tmp_path / "connector-registry.json"
    state = load_connector_registry(path)
    result = register_connector(
        state,
        "cninfo-announcement",
        status="supported",
        blocker="",
    )
    save_connector_registry(
        {**state, "connectors": result["connectors"], "usage": result["usage_map"]},
        path,
    )

    reloaded = load_connector_registry(path)
    entry = next(c for c in reloaded["connectors"] if c["id"] == "cninfo-announcement")
    assert entry["status"] == "supported"
    assert entry.get("blocker") == ""


def test_cli_path_override_reads_the_registry_it_writes(tmp_path: Path) -> None:
    path = tmp_path / "connector-registry.json"
    register = subprocess.run(
        [
            sys.executable,
            "-m",
            "loopx.cli",
            "connector",
            "register",
            "probe-cli",
            "--status",
            "supported",
            "--value-tier",
            "P0",
            "--layer",
            "L1",
            "--path",
            str(path),
            "--format",
            "json",
        ],
        check=True,
        cwd=Path.cwd(),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    assert json.loads(register.stdout)["ok"] is True

    listed = subprocess.run(
        [
            sys.executable,
            "-m",
            "loopx.cli",
            "connector",
            "list",
            "--path",
            str(path),
            "--format",
            "json",
        ],
        check=True,
        cwd=Path.cwd(),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    payload = json.loads(listed.stdout)
    assert any(row["id"] == "probe-cli" for row in payload["ranked"])

    ranked = subprocess.run(
        [
            sys.executable,
            "-m",
            "loopx.cli",
            "connector",
            "rank",
            "--path",
            str(path),
            "--format",
            "json",
        ],
        check=True,
        cwd=Path.cwd(),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    assert any(row["id"] == "probe-cli" for row in json.loads(ranked.stdout)["ranked"])
