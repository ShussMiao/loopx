#!/usr/bin/env python3
"""Thin TraeX host adapter for the LoopX governed Turn contract.

LoopX runs this adapter with one ``loopx_turn_host_request_v0`` JSON object on
stdin. The adapter:

1. extracts the bounded action text from the Turn envelope,
2. invokes one headless ``traex exec`` in the governed workspace,
3. asks TraeX for one schema-constrained public-safe result file,
4. emits exactly one ``loopx_turn_result_v0`` JSON object on stdout.

It does not read goal/todo state, build prompts from todo ids, write LoopX
state, spend quota, or validate its own work. Task body delivery and authority
stay in ``loopx turn run-once``; this is a dumb translation layer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from loopx.extensions.process_runtime import (  # noqa: E402
    CappedProcessResult,
    run_capped_process,
)
from loopx.control_plane.turn_driver.host_candidate import (  # noqa: E402
    COMPLETED_PHASES as COMPLETED_PHASES,
    LOOPX_TURN_HOST_REQUEST_SCHEMA,
    LOOPX_TURN_RESULT_SCHEMA as LOOPX_TURN_RESULT_SCHEMA,
    TEXT_LIMITS,
    build_result as build_host_result,
    extract_action_text as extract_action_text,
    extract_turn_authority,
)

TRAEX_OUTPUT_LIMIT_BYTES = 1_000_000

ACCEPTED_RESULT_KINDS = {
    "validated_progress",
    "repair_required",
    "replan_required",
    "user_action_required",
    "wait",
}
def render_prompt(authority: Mapping[str, Any]) -> str:
    """Wrap one signed Turn authority packet in the result-block framing.

    The model owns execution; the trailing block is the only channel the adapter
    reads back as a typed candidate. It stays public-safe and bounded.
    """

    authority_json = json.dumps(
        dict(authority),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "You are executing one bounded LoopX-governed work segment.\n"
        "The JSON below is the complete host authority for this Turn. Execute "
        "primary_action only after required_reads, write only inside write_scope, "
        "and obey workspace_guard. Do not infer authority from other prose.\n\n"
        f"Turn authority JSON:\n{authority_json}\n\n"
        "When finished, return only the schema-constrained result with these "
        "public-safe fields:\n"
        "- result_kind: one of validated_progress | repair_required | "
        "replan_required | user_action_required | wait\n"
        "- classification: short label (<=120 chars)\n"
        "- summary: what changed or why stopped (<=400 chars)\n"
        "- recommended_action: the bounded follow-up recommendation (<=1200 chars)\n"
        "- next_action: the concrete next step (<=1200 chars)\n"
        "- vision_unchanged_reason: why the goal path is unchanged (<=240 chars)\n"
        "Use repair_required when the task is sound but a recoverable defect "
        "blocks it, replan_required when this route is exhausted, and "
        "wait/user_action_required when no material write is safe. "
        "Do not include raw transcripts, credentials, or absolute local paths."
    )


def traex_result_schema() -> dict[str, Any]:
    properties = {
        "result_kind": {
            "type": "string",
            "enum": sorted(ACCEPTED_RESULT_KINDS),
        },
        **{
            field: {"type": "string", "maxLength": limit}
            for field, limit in TEXT_LIMITS.items()
        },
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def read_structured_result(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, dict)
        or str(value.get("result_kind") or "") not in ACCEPTED_RESULT_KINDS
    ):
        return None
    return value


def build_result(
    request: Mapping[str, Any],
    candidate: Mapping[str, Any] | None,
    *,
    fallback_reason: str = "",
) -> dict[str, Any]:
    """Shape a model result block into a valid loopx_turn_result_v0."""

    return build_host_result(
        request, candidate, host_name="TraeX",
        fallback_reason=fallback_reason or (
            "TraeX returned no typed result block; rerun or inspect the host session."
            if candidate is None else ""
        ),
    )


def run_traex(
    prompt: str,
    *,
    traex_bin: str,
    workspace: Path,
    schema_path: Path,
    output_path: Path,
    permission_mode: str | None,
    sandbox: str,
    model: str | None,
    timeout_seconds: float,
    skip_git_repo_check: bool,
) -> CappedProcessResult:
    argv: list[str] = [traex_bin, "exec"]
    if skip_git_repo_check:
        argv.append("--skip-git-repo-check")
    if permission_mode:
        argv.extend(["--permission-mode", permission_mode])
    argv.extend(["--sandbox", sandbox])
    argv.extend(["--output-schema", str(schema_path)])
    argv.extend(["--output-last-message", str(output_path)])
    if model:
        argv.extend(["-m", model])
    argv.append(prompt)
    return run_capped_process(
        argv,
        stdin=b"",
        cwd=workspace,
        timeout_seconds=max(1.0, timeout_seconds),
        output_limit_bytes=TRAEX_OUTPUT_LIMIT_BYTES,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traex-bin", default="traex")
    parser.add_argument("--workspace", default=os.getcwd())
    parser.add_argument(
        "--permission-mode",
        default=None,
        choices=("bypass_permissions", "custom"),
        help=(
            "Explicit TraeX exec permission mode. By default the adapter omits "
            "this flag so TraeX applies its non-interactive headless policy."
        ),
    )
    parser.add_argument(
        "--sandbox",
        default="workspace-write",
        choices=("read-only", "workspace-write", "danger-full-access"),
        help="TraeX sandbox; defaults to writes inside the governed workspace.",
    )
    parser.add_argument("-m", "--model", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument(
        "--no-skip-git-repo-check",
        dest="skip_git_repo_check",
        action="store_false",
    )
    args = parser.parse_args(argv)

    try:
        request = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"adapter: invalid request JSON on stdin: {exc}", file=sys.stderr)
        return 2
    if not isinstance(request, dict) or request.get("schema_version") != LOOPX_TURN_HOST_REQUEST_SCHEMA:
        print("adapter: stdin is not a loopx_turn_host_request_v0 object", file=sys.stderr)
        return 2

    try:
        authority = extract_turn_authority(request)
    except ValueError as exc:
        print(f"adapter: invalid TurnEnvelope authority: {exc}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="loopx-turn-traex-") as directory:
        temporary = Path(directory)
        schema_path = temporary / "result-schema.json"
        output_path = temporary / "last-message.json"
        schema_path.write_text(
            json.dumps(
                traex_result_schema(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        try:
            completed = run_traex(
                render_prompt(authority),
                traex_bin=args.traex_bin,
                workspace=Path(args.workspace),
                schema_path=schema_path,
                output_path=output_path,
                permission_mode=args.permission_mode,
                sandbox=args.sandbox,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                skip_git_repo_check=args.skip_git_repo_check,
            )
        except OSError as exc:
            print(f"adapter: traex exec failed: {type(exc).__name__}", file=sys.stderr)
            return 1

        if completed.failure_kind is not None:
            print(
                f"adapter: traex exec failed: {completed.failure_kind}",
                file=sys.stderr,
            )
            return 1
        if completed.returncode != 0:
            print(
                f"adapter: traex exited {completed.returncode}",
                file=sys.stderr,
            )
            return completed.returncode if completed.returncode > 0 else 1

        candidate = read_structured_result(output_path)
    result = build_result(request, candidate)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
