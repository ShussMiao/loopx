from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .simulator import execute_simulated_finance_operation


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loopx-finance-execution")
    parser.add_argument("--doctor", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.doctor:
        return 0
    try:
        request = json.load(sys.stdin)
        result = execute_simulated_finance_operation(request)
    except Exception as exc:  # noqa: BLE001 - redact the process boundary
        print(
            json.dumps(
                {
                    "ok": False,
                    "schema_version": "finance_operation_error_v0",
                    "error": type(exc).__name__,
                    "simulation": True,
                    "external_write_performed": False,
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
