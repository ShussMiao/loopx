from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("scheme", "default_port", "other_port"),
    [("ssh", 22, 443), ("https", 443, 22), ("git", 9418, 80)],
)
def test_project_cli_distinguishes_nondefault_repository_ports(
    tmp_path: Path, scheme: str, default_port: int, other_port: int
) -> None:
    registry = tmp_path / "registry.json"
    env = {key: value for key, value in os.environ.items() if not key.startswith("LOOPX_")}

    def run(*args: str) -> tuple[int, dict]:
        result = subprocess.run(
            [
                sys.executable, "-m", "loopx.cli", "--format", "json",
                "--registry", str(registry), "--runtime-root", str(tmp_path / "runtime"),
                "project", *args,
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        assert result.stdout, result.stderr
        return result.returncode, json.loads(result.stdout)

    ordinary = f"{scheme}://code.example.com/team/repo.git"
    separate = f"{scheme}://code.example.com:{other_port}/team/repo.git"
    for project_id, remote in [("ordinary", ordinary), ("separate", separate)]:
        code, payload = run(
            "register", "--project-id", project_id, "--project-kind", "work",
            "--knowledge-root", str(tmp_path / project_id), "--goal-id", project_id,
            "--objective", "Inspect the synthetic repository.",
            "--acceptance", "Resolve only the matching repository endpoint.",
            "--next-effect", "Read the repository identity.",
            "--stop-condition", "Stop before remote access.",
            "--repository", remote,
        )
        assert code == 0, payload

    before = registry.read_bytes()
    for remote, expected in [
        (ordinary, "ordinary"),
        (f"{scheme}://code.example.com:{default_port}/team/repo.git", "ordinary"),
        (separate, "separate"),
    ]:
        code, payload = run("resolve", "--repository", remote)
        assert code == 0, payload
        assert payload["resolution"] == "resolved"
        assert payload["project_id"] == expected
    assert registry.read_bytes() == before
    projects = json.loads(before)["projects"]
    assert [project["repository_bindings"] for project in projects] == [
        ["git:code.example.com/team/repo"],
        [f"git:code.example.com:{other_port}/team/repo"],
    ]
