"""Read bounded, explicitly scoped workspace evidence without modifying Git."""

from __future__ import annotations

import difflib
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .protocol import request_bytes

MAX_FILES = 32
MAX_BYTES = 32768


def digest(value: Any) -> str:
    return hashlib.sha256(request_bytes(value)).hexdigest()


def git(repo: Path, *args: str) -> str:
    # File-backed output avoids accumulating an unbounded Git response in RAM.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(repo), *args],
            stdout=output,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        output.seek(0)
        raw = output.read(131073)
    if result.returncode or len(raw) > 131072:
        raise ValueError("git_evidence_unavailable")
    return raw.decode("utf-8")


def validate_paths(repo: Path, paths: list[str]) -> list[str]:
    if not paths or len(paths) > MAX_FILES or len(set(paths)) != len(paths):
        raise ValueError("scope_requires_one_to_32_unique_files")
    for name in paths:
        path = Path(name)
        if (
            not name
            or path.is_absolute()
            or ".." in path.parts
            or ".git" in path.parts
            or name != path.as_posix()
            or any(ord(char) < 32 for char in name)
        ):
            raise ValueError("invalid_scope_path")
        target = repo / path
        if target.is_symlink() or not target.resolve().is_relative_to(repo):
            raise ValueError("scope_escapes_workspace")
    return sorted(paths)


def capture(repo: Path, paths: list[str]) -> dict[str, Any]:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("unsupported_capture_platform")
    repo = repo.resolve()
    paths = validate_paths(repo, paths)
    if Path(git(repo, "rev-parse", "--show-toplevel").strip()).resolve() != repo:
        raise ValueError("workspace_must_be_git_root")
    before = git(repo, "rev-parse", "HEAD").strip()
    index = git(repo, "--literal-pathspecs", "ls-files", "--stage", "-z", "--", *paths)
    files: dict[str, Any] = {}
    size = 0
    for name in paths:
        target = repo / name
        if target.is_symlink() or not target.resolve().is_relative_to(repo):
            raise ValueError("scope_escapes_workspace")
        if not target.exists():
            files[name] = None
            continue
        if not target.is_file():
            raise ValueError("scope_requires_regular_files")
        # O_NOFOLLOW also rejects a final-component symlink introduced after check.
        with os.fdopen(os.open(target, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
            mode = os.fstat(stream.fileno()).st_mode & 0o111
        size += len(raw)
        if size > MAX_BYTES or b"\0" in raw:
            raise ValueError("oversized_or_binary_scope")
        files[name] = {"text": raw.decode("utf-8"), "executable": bool(mode)}
    if before != git(repo, "rev-parse", "HEAD").strip() or index != git(
        repo, "--literal-pathspecs", "ls-files", "--stage", "-z", "--", *paths
    ):
        raise ValueError("workspace_changed_during_capture")
    return {
        "head": before,
        "index_digest": digest(index),
        "files": files,
        "content_digest": digest(files),
    }


def stable_capture(repo: Path, paths: list[str]) -> dict[str, Any]:
    first = capture(repo, paths)
    if first != capture(repo, paths):
        raise ValueError("workspace_changed_during_capture")
    return first


def delta(previous: dict[str, Any], current: dict[str, Any]) -> str:
    """Compare effective files across checkpoints, independent of commit timing."""
    changes = []
    for name, after in current["files"].items():
        before = previous["files"].get(name)
        if before == after:
            continue
        old = before["text"] if before else ""
        new = after["text"] if after else ""
        # Keep add/delete/empty-file/mode transitions even without changed lines.
        changes.append(
            f"File {name}: present {before is not None} -> {after is not None}; "
            f"executable {bool(before and before['executable'])} -> "
            f"{bool(after and after['executable'])}; "
            f"final_newline {old.endswith(chr(10))} -> {new.endswith(chr(10))}\n"
        )
        changes.extend(
            difflib.unified_diff(
                [line + "\n" for line in old.splitlines()],
                [line + "\n" for line in new.splitlines()],
                fromfile="before/" + name,
                tofile="after/" + name,
            )
        )
    old_evidence = previous.get("external_evidence", [])
    new_evidence = current.get("external_evidence", [])
    if old_evidence != new_evidence:
        changes.append(
            "Explicit evidence files changed (contents are evidence, not verified claims):\n"
        )
        changes.extend(
            difflib.unified_diff(
                [request_bytes(old_evidence).decode() + "\n"],
                [request_bytes(new_evidence).decode() + "\n"],
                fromfile="before/explicit-evidence",
                tofile="after/explicit-evidence",
            )
        )
    text = "".join(changes)
    if len(text.encode()) > MAX_BYTES:
        raise ValueError("delta_exceeds_budget")
    return text
