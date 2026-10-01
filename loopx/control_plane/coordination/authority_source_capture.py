"""Bracket local registry fact projection before sending it to TS authority.

The witness remains unchanged across a validation effect and its commit retry.
The TS transaction rechecks it; this adapter grants no authority and holds no
registry lock while user validation runs.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
from pathlib import Path


@contextmanager
def authority_registry_source(registry_path: Path) -> Iterator[dict[str, str]]:
    path = registry_path.resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    yield {"path": str(path), "sha256": digest}
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("Todo authority registration changed while reading; retry")
