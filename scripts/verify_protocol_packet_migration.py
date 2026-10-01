#!/usr/bin/env python3
"""Check new quota outputs and frozen v0 history with an unmodified v1.1.0 reader.

Prepare that checkout and its Node dependencies explicitly. This command never
fetches sources, installs dependencies, writes receipts, or changes the checkout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loopx.control_plane.effect_program import ReceiptBoundReplayPhase  # noqa: E402
from loopx.control_plane.quota.should_run import build_quota_should_run  # noqa: E402
from loopx.control_plane.quota.turn_envelope import build_turn_envelope  # noqa: E402
from loopx.control_plane.testing.quota_fixtures import quota_status_payload  # noqa: E402

READER_REVISION = "607c11d75e9d608e44d9caf6b675b32c0abb8267"
READER = '''
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
import loopx
assert Path(loopx.__file__).resolve().is_relative_to(root), "wrong reader source"
from loopx.control_plane.effect_program import interpret_quota_should_run_packet
from loopx.control_plane.quota.turn_envelope import quota_action_signature_document, turn_envelope_action_signature_document
from loopx.control_plane.turn_driver.host_candidate import extract_turn_authority
cases = json.load(sys.stdin)
for case in cases:
    decision, envelope = case["decision"], case["envelope"]
    before = json.dumps(case, sort_keys=True)
    turn = interpret_quota_should_run_packet(decision)
    assert turn.observation.should_run == decision["should_run"], case["id"]
    assert turn.observation.protocol_summary == decision.get("protocol_action_packet", {}).get("summary"), case["id"]
    assert quota_action_signature_document(decision) == turn_envelope_action_signature_document(envelope), case["id"]
    assert extract_turn_authority({"turn_envelope": envelope})["primary_action"], case["id"]
    assert json.dumps(case, sort_keys=True) == before, case["id"]
print(json.dumps({"reader_cases": len(cases), "ok": True}))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader-checkout", type=Path, required=True)
    args = parser.parse_args()
    reader = args.reader_checkout.resolve()
    revision = subprocess.check_output(["git", "-C", str(reader), "rev-parse", "HEAD"], text=True).strip()
    if revision != READER_REVISION:
        parser.error(f"reader checkout must be v1.1.0 commit {READER_REVISION}; got {revision}")
    clean = subprocess.run(["git", "-C", str(reader), "diff", "--quiet", "HEAD", "--", "loopx"])
    if clean.returncode:
        parser.error("reader checkout has modified runtime sources; use unmodified v1.1.0")
    history = json.loads((ROOT / "tests/fixtures/protocol_packet_history_v0.json").read_text(encoding="utf-8"))
    cases = [{"id": c["id"], "decision": c["decision"], "envelope": c["envelope"]} for c in history["cases"]]
    for state in ("eligible", "paused", "operator_gate", "exhausted"):
        for settled in (False, True):
            status = quota_status_payload(
                goal_id="migration-reader-fixture", status="active", quota_state=state,
                recommended_action="Verify the bounded migration",
            )
            decision = build_quota_should_run(
                status, goal_id="migration-reader-fixture", available_capabilities=["shell"],
                receipt_bound_replay_phase=ReceiptBoundReplayPhase.SETTLED if settled else None,
            )
            assert "protocol_action_packet" not in decision
            cases.append({"id": f"new/{state}/{settled}", "decision": decision, "envelope": build_turn_envelope(decision)})
    result = subprocess.run(
        [sys.executable, "-I", "-c", READER, str(reader)], cwd=reader,
        input=json.dumps(cases), capture_output=True, text=True, timeout=120,
    )
    if result.returncode:
        raise RuntimeError(f"v1.1.0 readback failed:\n{result.stdout}\n{result.stderr}")
    report = json.loads(result.stdout)
    assert report == {"reader_cases": len(cases), "ok": True}
    print(json.dumps({**report, "new_outputs": 8, "frozen_history": len(history["cases"]), "reader_sha": revision}))


if __name__ == "__main__":
    main()
