#!/usr/bin/env python3
"""Generate or verify the tracked project-registry I/O census."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from loopx.semantics.project_registry_io import (  # noqa: E402
    PROJECT_REGISTRY_IO_MANIFEST,
    build_project_registry_io_manifest,
    render_project_registry_io_manifest,
    validate_project_registry_io_manifest,
)


def _load(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"manifest root must be an object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = ROOT
    output = args.output or root / PROJECT_REGISTRY_IO_MANIFEST
    previous = _load(output)
    if args.check:
        if previous is None:
            raise SystemExit(f"project registry I/O manifest is missing: {output}")
        errors = validate_project_registry_io_manifest(root, previous)
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"project registry I/O manifest is current: {len(previous['sites'])} sites")
        return 0

    manifest = build_project_registry_io_manifest(root, previous=previous)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_project_registry_io_manifest(manifest),
        encoding="utf-8",
    )
    unclassified = [
        row["site"]
        for row in manifest["sites"]
        if row["classification"] == "unclassified"
    ]
    print(
        f"wrote {output.relative_to(root)} with {len(manifest['sites'])} sites "
        f"and {len(unclassified)} unclassified direct sites"
    )
    return 1 if unclassified else 0


if __name__ == "__main__":
    raise SystemExit(main())
