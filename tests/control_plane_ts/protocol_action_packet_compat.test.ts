import assert from "node:assert/strict";
import test from "node:test";

import { interpretQuotaShouldRunPacket, type JsonObject } from "../../loopx/control_plane/effect_program.ts";
import {
  buildTurnEnvelope,
  quotaActionSignatureDocument,
  turnEnvelopeActionSignatureDocument,
} from "../../loopx/control_plane/quota/turn_envelope.ts";

// Synthetic v0 input using the ordered wire fields introduced by PR #1898
// (fa1a7099400841568d082abc1f60b410311c8945, interaction_contract.py).
// Do not derive this input from the current packet writer. The summary is
// observational: it cannot override the typed action or confer spend authority.
const historicalSummary = "actor=agent user_action_required=false agent_action_required=true " +
  "quiet_noop_allowed=false llm=no_api agent_action=inspect the fixture";
const semanticFields = {
  actor: "agent", user_action_required: false, agent_action_required: true,
  quiet_noop_allowed: false, llm: "no_api", agent_action: "inspect the fixture",
};

function decision(summary?: string): JsonObject {
  return {
    ok: true, goal_id: "compat-goal", agent_identity: { agent_id: "compat-agent" },
    decision: "run", should_run: true, effective_action: "normal_run",
    interaction_contract: {
      schema_version: "loopx_interaction_contract_v0", mode: "bounded_delivery",
      user_channel: { action_required: false, notify: "DONT_NOTIFY" },
      agent_channel: {
        must_attempt: true, delivery_allowed: true, quiet_noop_allowed: false,
        primary_action: "inspect the fixture",
      },
      cli_channel: {
        next_cli_actions: ["loopx status --goal-id compat-goal"],
        spend_allowed_now: false, spend_after_validation: true,
      },
    },
    ...(summary === undefined ? {} : {
      protocol_action_packet: { schema_version: "protocol_action_packet_v0", summary },
    }),
  };
}

for (const [name, summary, status] of [
  ["absent", undefined, undefined],
  ["historical-v0", historicalSummary, "verified"],
  ["opaque-v0", "legacy opaque packet", "unverified_retain_summary"],
] as const) {
  test(`${name}: the real TS reader preserves actions and the envelope witness`, () => {
    const source = decision(summary);
    const before = structuredClone(source);
    const turn = interpretQuotaShouldRunPacket(source);
    assert.equal(turn.observation.protocol_summary, summary ?? null);
    assert.equal(turn.observation.effective_action, "normal_run");
    assert.equal(turn.observation.should_run, true);
    assert.deepEqual(turn.next_effect.cli_actions, ["loopx status --goal-id compat-goal"]);

    const envelope = buildTurnEnvelope({
      payload: source, protocol_action_fields: semanticFields, scheduler_execution_args: "",
    });
    assert.equal((envelope.action as JsonObject).primary_action, "inspect the fixture");
    assert.equal((envelope.writeback as JsonObject).spend_allowed_now, false);
    const witness = (envelope.contract_capsule as JsonObject).protocol_action_packet as JsonObject | undefined;
    if (status === undefined) {
      assert.equal(witness, undefined);
    } else {
      assert.equal(witness?.derivation_status, status);
      assert.equal(witness?.reconstruction_verified, name === "historical-v0");
      assert.equal(witness?.summary, name === "opaque-v0" ? summary : undefined);
    }
    const signed = quotaActionSignatureDocument(source, semanticFields);
    assert.deepEqual(turnEnvelopeActionSignatureDocument(envelope), signed);
    // Hash labels are diagnostic input, not the semantic document. Tampering
    // must change the real reader's document even if matches stays true.
    (envelope.writeback as JsonObject).spend_allowed_now = true;
    assert.equal((envelope.action_signature as JsonObject).matches, true);
    assert.notDeepEqual(turnEnvelopeActionSignatureDocument(envelope), signed);
    assert.deepEqual(source, before);
  });
}

test("v0 residue preserves the old witness without replacing the current action", () => {
  const source = decision(historicalSummary);
  ((source.interaction_contract as JsonObject).agent_channel as JsonObject).primary_action = "inspect the updated fixture";
  const envelope = buildTurnEnvelope({
    payload: source, protocol_action_fields: semanticFields, scheduler_execution_args: "",
  });
  const witness = (envelope.contract_capsule as JsonObject).protocol_action_packet as JsonObject;
  assert.equal((envelope.action as JsonObject).primary_action, "inspect the updated fixture");
  assert.equal(witness.derivation_status, "verified_with_residue");
  assert.equal(witness.reconstruction_verified, true);
  assert.deepEqual(witness.residue, { agent_action: "inspect the fixture" });
  assert.equal(witness.summary, undefined);
  const signed = quotaActionSignatureDocument(source, semanticFields);
  assert.deepEqual(turnEnvelopeActionSignatureDocument(envelope), signed);
  delete witness.residue;
  assert.notDeepEqual(turnEnvelopeActionSignatureDocument(envelope), signed);
});

test("missing semantic projection retains v0 summary as unverified fallback", () => {
  const envelope = buildTurnEnvelope({
    payload: decision(historicalSummary), protocol_action_fields: {}, scheduler_execution_args: "",
  });
  const witness = (envelope.contract_capsule as JsonObject).protocol_action_packet as JsonObject;
  assert.equal(witness.derivation_status, "unverified_retain_summary");
  assert.equal(witness.reconstruction_verified, false);
  assert.equal(witness.summary, historicalSummary);
  assert.equal((envelope.action as JsonObject).primary_action, "inspect the fixture");
  assert.equal((envelope.writeback as JsonObject).spend_allowed_now, false);
});
