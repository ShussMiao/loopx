import type {JsonObject} from "../effect_program.ts";
import {requireStringLiteral} from "../runtime_decode.ts";
import {
  canonicalAuthorityBytes,
  canonicalAuthoritySha256,
} from "./authority_store_codec.ts";
import {
  indexCoordinationProjection,
  validateCoordinationTodoReadModel,
} from "./coordination_projection.ts";
import {
  HANDOFF_MODES,
  type HandoffMode,
} from "./handoff_mode_policy.ts";
import {canonicalTaskLease, canonicalLeaseTodoFact} from "./task_lease_state.ts";
import {leaseOwnerRejection} from "../work_items/task_lease_eligibility.ts";
import {leaseEpoch, leaseIsActive, leaseVersion} from "../work_items/task_lease_acquire.ts";
import {normalizeRegisteredTodoAgents, normalizeTodoAgent} from "./todo_agents.ts";
import {coordinationTodoWriteScopes} from "./todo_write_scopes.ts";

export const PROMOTION_HANDOFF_MODE_MIGRATIONS = [
  "require_existing_hard_lease",
  "preserve",
  "hard_lease",
] as const;
export type PromotionHandoffModeMigration = typeof PROMOTION_HANDOFF_MODE_MIGRATIONS[number];

export interface PromotionHandoffMigrationPlan {
  readonly ready: boolean;
  readonly reason_code?: string;
  readonly reason?: string;
  readonly strategy: PromotionHandoffModeMigration;
  readonly previous_mode: HandoffMode;
  readonly target_mode: HandoffMode;
  readonly changed: boolean;
  readonly preserved_claims: readonly JsonObject[];
  readonly lease_dispositions: readonly JsonObject[];
  readonly conflicts: readonly JsonObject[];
  readonly target_projection: JsonObject;
  readonly target_projection_sha256: string;
}

export function normalizePromotionHandoffModeMigration(
  value: unknown,
): PromotionHandoffModeMigration {
  return requireStringLiteral(
    value ?? "require_existing_hard_lease",
    PROMOTION_HANDOFF_MODE_MIGRATIONS,
    "handoff_mode_migration",
  );
}

/**
 * Plan the ownership-policy part of a reviewed authority promotion.
 *
 * Claims remain assignment facts. Moving to hard_lease never invents a live
 * execution lease; the original owner must acquire one through the ordinary
 * atomic claim+lease path before its next protected write.
 */
export function planPromotionHandoffMigration(
  head: JsonObject,
  goalId: string,
  strategyValue: unknown,
  registeredAgentsValue: readonly string[],
  observedAt: Date,
): PromotionHandoffMigrationPlan {
  const strategy = normalizePromotionHandoffModeMigration(strategyValue);
  const registeredAgents = normalizeRegisteredTodoAgents(registeredAgentsValue);
  const indexed = indexCoordinationProjection(head, goalId);
  validateCoordinationTodoReadModel(head, goalId);
  const previousMode = requireStringLiteral(
    head.handoff_mode ?? "legacy",
    HANDOFF_MODES,
    "promotion source handoff_mode",
  );
  const targetMode: HandoffMode =
    strategy === "require_existing_hard_lease" || strategy === "hard_lease"
      ? "hard_lease"
      : previousMode;
  const conflicts: JsonObject[] = [];
  const validatesMigrationOwnership = strategy !== "require_existing_hard_lease";
  if (strategy === "require_existing_hard_lease" && previousMode !== "hard_lease") {
    conflicts.push({
      kind: "source_mode_mismatch",
      reason_code: "local_authority_promotion_requires_hard_lease",
      previous_mode: previousMode,
      required_mode: "hard_lease",
    });
  }

  const preservedClaims = [...indexed.todos.values()]
    .filter((todo) => todo.archive_state === "active" && todo.done !== true &&
      typeof todo.claimed_by === "string" && todo.claimed_by.trim().length > 0)
    .map((todo) => {
      const claimedBy = normalizeTodoAgent(todo.claimed_by, "todo.claimed_by");
      if (validatesMigrationOwnership && !registeredAgents.includes(claimedBy)) {
        conflicts.push({
          kind: "claim_owner_not_registered",
          reason_code: "claim_owner_not_registered",
          todo_id: todo.todo_id,
          claimed_by: claimedBy,
        });
      }
      return {
        todo_id: todo.todo_id,
        claimed_by: claimedBy,
        status: todo.status,
        disposition: targetMode === "hard_lease"
          ? "preserved_assignment_requires_lease"
          : "preserved_assignment",
      };
    });

  const leaseDispositions: JsonObject[] = [];
  for (const [todoId, rawLease] of indexed.leases) {
    const lease = canonicalTaskLease(rawLease, goalId, todoId);
    const active = leaseIsActive(lease, observedAt);
    let disposition = lease.status === "released"
      ? "preserved_released"
      : active ? "preserved_active" : "preserved_expired";
    if (validatesMigrationOwnership && active && targetMode === "soft_claim") {
      conflicts.push({
        kind: "active_lease_incompatible_with_soft_claim",
        reason_code: "active_lease_incompatible_with_soft_claim",
        todo_id: todoId,
        owner: lease.owner,
        target_mode: targetMode,
      });
      disposition = "conflict";
    } else if (validatesMigrationOwnership && active) {
      const todo = canonicalLeaseTodoFact(indexed.todos.get(todoId));
      const owner = normalizeTodoAgent(lease.owner, "lease.owner");
      const rejection = leaseOwnerRejection(todo, owner, registeredAgents);
      const expectedScopes = coordinationTodoWriteScopes(indexed.todos.get(todoId)!);
      const observedScopes = Array.isArray(lease.write_scopes) ? lease.write_scopes : [];
      const scopeMatch = canonicalAuthorityBytes(expectedScopes).equals(
        canonicalAuthorityBytes(observedScopes),
      );
      if (rejection !== null || !scopeMatch) {
        conflicts.push({
          kind: "active_lease_not_safe_to_preserve",
          todo_id: todoId,
          owner,
          reason_code: rejection ?? "active_lease_scope_mismatch",
          scope_match: scopeMatch,
        });
        disposition = "conflict";
      }
      // Validate both fencing counters even when they are zero/defaulted.
      leaseVersion(lease);
      leaseEpoch(lease);
    }
    leaseDispositions.push({
      todo_id: todoId,
      owner: lease.owner,
      status: lease.status,
      active,
      version: leaseVersion(lease),
      lease_epoch: leaseEpoch(lease),
      disposition,
    });
  }

  const targetProjection = previousMode === targetMode ? head : {...head, handoff_mode: targetMode};
  const firstConflict = conflicts[0];
  return {
    ready: conflicts.length === 0,
    ...(firstConflict === undefined ? {} : {
      reason_code: String(firstConflict.reason_code ?? "handoff_mode_migration_conflict"),
      reason: "claim or lease facts cannot be preserved under the requested handoff-mode migration",
    }),
    strategy,
    previous_mode: previousMode,
    target_mode: targetMode,
    changed: previousMode !== targetMode,
    preserved_claims: preservedClaims,
    lease_dispositions: leaseDispositions,
    conflicts,
    target_projection: targetProjection,
    target_projection_sha256: canonicalAuthoritySha256(targetProjection),
  };
}

export function publicPromotionHandoffMigrationPlan(
  plan: PromotionHandoffMigrationPlan,
): JsonObject {
  return {
    schema_version: "loopx_promotion_handoff_migration_plan_v0",
    ready: plan.ready,
    ...(plan.reason_code === undefined ? {} : {reason_code: plan.reason_code}),
    ...(plan.reason === undefined ? {} : {reason: plan.reason}),
    strategy: plan.strategy,
    previous_mode: plan.previous_mode,
    target_mode: plan.target_mode,
    changed: plan.changed,
    preserved_claim_count: plan.preserved_claims.length,
    preserved_claims: [...plan.preserved_claims],
    lease_dispositions: [...plan.lease_dispositions],
    conflicts: [...plan.conflicts],
    target_projection_sha256: plan.target_projection_sha256,
  };
}
