import assert from "node:assert/strict";
import test from "node:test";

import type {JsonObject} from "../../loopx/control_plane/effect_program.ts";
import {
  planPromotionHandoffMigration,
} from "../../loopx/control_plane/coordination/promotion_handoff_migration.ts";
import {projection, todo} from "./shadow_file_fixture.ts";

const agents = ["agent-a", "agent-b"];
const observedAt = new Date("2026-09-21T12:00:00Z");

function claimedTodo(index: number, owner = "agent-a"): JsonObject {
  return {
    ...todo(`todo_${String(index).padStart(2, "0")}`),
    claimed_by: owner,
    required_write_scopes: ["src/**"],
  };
}

function activeLease(todoId: string, owner = "agent-a"): JsonObject {
  return {
    schema_version: "task_lease_v0",
    goal_id: "goal-a",
    todo_id: todoId,
    owner,
    idempotency_key: `turn:${todoId}`,
    write_scopes: ["src/**"],
    acquire_ttl_seconds: 2700,
    version: 2,
    lease_epoch: 3,
    status: "active",
    acquired_at: "2026-09-21T11:30:00Z",
    updated_at: "2026-09-21T11:30:00Z",
    expires_at: "2026-09-21T12:30:00Z",
  };
}

test("explicit legacy to hard_lease migration preserves fifty claims without inventing leases", () => {
  const todos = Array.from({length: 50}, (_, index) => claimedTodo(index));
  const plan = planPromotionHandoffMigration(
    projection(todos, [], "legacy"),
    "goal-a",
    "hard_lease",
    agents,
    observedAt,
  );
  assert.equal(plan.ready, true, JSON.stringify(plan));
  assert.equal(plan.previous_mode, "legacy");
  assert.equal(plan.target_mode, "hard_lease");
  assert.equal(plan.preserved_claims.length, 50);
  assert.equal(plan.lease_dispositions.length, 0);
  assert.equal(plan.target_projection.handoff_mode, "hard_lease");
  assert.ok(plan.preserved_claims.every(
    (claim) => claim.disposition === "preserved_assignment_requires_lease",
  ));
});

test("preserve canonicalizes each existing mode without changing ownership policy", () => {
  for (const mode of ["legacy", "soft_claim", "hard_lease"] as const) {
    const head = projection([claimedTodo(1)], [], mode);
    const plan = planPromotionHandoffMigration(head, "goal-a", "preserve", agents, observedAt);
    assert.equal(plan.ready, true, JSON.stringify(plan));
    assert.equal(plan.target_mode, mode);
    assert.equal(plan.changed, false);
    assert.equal(plan.target_projection, head);
  }
});

test("safe active same-owner lease is retained with its fencing identity", () => {
  const lease = activeLease("todo_01");
  const plan = planPromotionHandoffMigration(
    projection([claimedTodo(1)], [lease], "legacy"),
    "goal-a",
    "hard_lease",
    agents,
    observedAt,
  );
  assert.equal(plan.ready, true, JSON.stringify(plan));
  assert.deepEqual(plan.lease_dispositions, [{
    todo_id: "todo_01",
    owner: "agent-a",
    status: "active",
    active: true,
    version: 2,
    lease_epoch: 3,
    disposition: "preserved_active",
  }]);
});

test("keep-mode rejects an active lease that contradicts soft_claim semantics", () => {
  const plan = planPromotionHandoffMigration(
    projection([claimedTodo(1)], [activeLease("todo_01")], "soft_claim"),
    "goal-a",
    "preserve",
    agents,
    observedAt,
  );
  assert.equal(plan.ready, false);
  assert.equal(plan.conflicts[0]?.kind, "active_lease_incompatible_with_soft_claim");
});

test("active lease owner or scope mismatch fails the reviewed migration", () => {
  for (const lease of [
    activeLease("todo_01", "agent-b"),
    {...activeLease("todo_01"), write_scopes: ["docs/**"]},
  ]) {
    const plan = planPromotionHandoffMigration(
      projection([claimedTodo(1)], [lease], "legacy"),
      "goal-a",
      "hard_lease",
      agents,
      observedAt,
    );
    assert.equal(plan.ready, false);
    assert.equal(plan.conflicts[0]?.kind, "active_lease_not_safe_to_preserve");
  }
});

test("explicit migration fails before fencing when a live claim owner is unregistered", () => {
  const plan = planPromotionHandoffMigration(
    projection([claimedTodo(1, "agent-c")], [], "legacy"),
    "goal-a",
    "hard_lease",
    agents,
    observedAt,
  );
  assert.equal(plan.ready, false);
  assert.deepEqual(plan.conflicts, [{
    kind: "claim_owner_not_registered",
    reason_code: "claim_owner_not_registered",
    todo_id: "todo_01",
    claimed_by: "agent-c",
  }]);
});

test("explicit migration rejects unsupported downgrade strategies", () => {
  assert.throws(
    () => planPromotionHandoffMigration(
      projection([claimedTodo(1)], [activeLease("todo_01")], "hard_lease"),
      "goal-a",
      "soft_claim",
      agents,
      observedAt,
    ),
    /handoff_mode_migration/,
  );
});
