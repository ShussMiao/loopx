import type {JsonObject} from "../../loopx/control_plane/effect_program.ts";
import {planCoordinationTodoCreate} from "../../loopx/control_plane/coordination/todo_create.ts";
import {TODO_DOMAIN_ITEM_SCHEMA, TODO_DOMAIN_READ_RECORD_SCHEMA} from "../../loopx/control_plane/coordination/coordination_state_contract.ts";
import {readFileSync} from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";
import {planTodoPriority, readTodoPriority, todoPriorityRank} from "../../loopx/control_plane/todos/priority.ts";

test("priority is declared metadata; prose is never scheduling input", () => {
  assert.equal(readTodoPriority({text: "Investigate P0 parser behavior"}), null);
  assert.equal(readTodoPriority({priority: "P3", text: "[P0] stale display"}), "P3");
  assert.equal(readTodoPriority({priority: null, text: "[P0] stale display"}), null);
  assert.equal(readTodoPriority({text: "[P1-user] Approve access"}), "P1");
  assert.equal(todoPriorityRank("P4"), 4);
  assert.equal(todoPriorityRank(null), 50);
});

test("authoring preserves omission, explicit clear and conflict semantics", () => {
  const old = {text: "[P2] Existing task", priority: "P2"};
  assert.deepEqual(planTodoPriority(old, {text: "Renamed task"}),
    {text: "[P2] Renamed task", title: "Renamed task", priority: "P2"});
  assert.deepEqual(planTodoPriority(old, {priority: "P0"}),
    {text: "[P0] Existing task", title: "Existing task", priority: "P0"});
  assert.deepEqual(planTodoPriority(old, {clear_priority: true}),
    {text: "Existing task", title: "Existing task", priority: null});
  assert.deepEqual(planTodoPriority(old, {}), {});
  assert.equal(planTodoPriority({}, {text: "Unprioritized task"}).priority, null);
  assert.equal(planTodoPriority({}, {text: "[P1parser] Literal text"}).text, "[P1parser] Literal text");
  assert.equal(planTodoPriority(old, {text: "[P3] Legacy edit"}).priority, "P3");
  assert.throws(() => planTodoPriority(old, {priority: "P0", text: "[P1] Conflict"}), /conflict/);
  assert.throws(() => planTodoPriority(old, {priority: "P0", clear_priority: true}), /either/);
  for (const priority of ["P5", "P1junk", "P1-user", 1, false, ""]) {
    assert.throws(() => planTodoPriority({}, {text: "Task", priority}), /priority/);
  }
});


test("complex fixture priority vocabulary matches the compatibility codec", () => {
  const fixture = JSON.parse(readFileSync(new URL("../fixtures/control_plane/coordination_production_scale_v0.json", import.meta.url), "utf8"));
  for (const row of fixture.priority_cases) {
    assert.equal(readTodoPriority(row.item), row.priority);
    assert.equal(todoPriorityRank(readTodoPriority(row.item)), row.rank);
  }
});


test("canonical create normalizes before duplicate matching and clears absent priority", () => {
  const input = {goal_id: "priority-goal", actor_agent_id: null, registered_agents: [],
    operation_id: "create-priority", dry_run: false, now: new Date("2026-09-20T00:00:00Z"),
    todo: {schema_version: TODO_DOMAIN_ITEM_SCHEMA, todo_id: "new-todo", role: "agent",
      status: "open", done: false, archive_state: "active", text: "A task", priority: "P4"}};
  const first = planCoordinationTodoCreate(input, new Map(), TODO_DOMAIN_READ_RECORD_SCHEMA);
  assert.equal(first.status, "planned");
  const created = first.todo as JsonObject;
  assert.equal(created.priority, "P4"); assert.equal(created.text, "[P4] A task");
  const duplicate = planCoordinationTodoCreate({...input, todo: {...input.todo, todo_id: "other-todo"}},
    new Map([["new-todo", created]]), TODO_DOMAIN_READ_RECORD_SCHEMA);
  assert.equal(duplicate.changed, false);
  assert.equal(duplicate.todo_id, "new-todo");
  const unranked = planCoordinationTodoCreate({...input, todo: {...input.todo, priority: null}},
    new Map(), TODO_DOMAIN_READ_RECORD_SCHEMA).todo as JsonObject;
  assert.equal(unranked.priority, undefined); assert.equal(unranked.text, "A task");
});
