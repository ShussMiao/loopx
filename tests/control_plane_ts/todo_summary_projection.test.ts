import assert from "node:assert/strict";
import test from "node:test";
import type {JsonObject} from "../../loopx/control_plane/effect_program.ts";
import {TODO_SUMMARY_PROJECTION_COLUMNS, projectTodoSummary} from "../../loopx/control_plane/todos/summary_projection.ts";
import {productionScaleCoordinationFixture} from "./production_scale_coordination_fixture.ts";

const row = (fields: JsonObject = {}): JsonObject => ({status: "open", done: false,
  task_class: "advancement_task", has_resume: false, resume_ready: null, resume_evaluated: false,
  acceptance_blocked: false, claimed: false, claim: null, preferred: false, watch_only: false,
  due_at: null, expires_at: null, sort: [1, 1, "", ""], todo_id: null, bound: null,
  blocks: null, global: false, excluded: [], completed_at: null, updated_at: null,
  completion_index: 0, linked_user_action: false, no_followup: false,
  successor_gap: false, handoff_state: null, replan: false, ...fields});
const request = (rows: JsonObject[], fields: JsonObject = {}): JsonObject => ({
  schema_version: "todo_summary_projection_request_v1",
  columns: [...TODO_SUMMARY_PROJECTION_COLUMNS],
  rows: rows.map(row => TODO_SUMMARY_PROJECTION_COLUMNS.map(name => row[name] ?? null)),
  observed_at: 100,
  selection: null, role: "agent", source_section: "Agent Todo", item_limit: 12, full_selection: true, ...fields});
const done = (fields: JsonObject = {}) => row({status: "done", done: true, no_followup: true, ...fields});

test("one whole-source projection computes counts, visibility and closure before limits", () => {
  for (const limit of [null, 0, 1, 12]) {
    const rows = Array.from({length: 32}, (_, index) => row({claimed: true, claim: index < 24 ? "a" : "b"}));
    const before = structuredClone(rows), result = projectTodoSummary(request(rows, {item_limit: limit}));
    assert.equal(result.fields.open_count, 32);
    assert.equal((result.fields.work_counts as JsonObject).advancement, 32);
    assert.equal(result.fields.claimed_open_count, 32);
    assert.deepEqual(result.lanes.claimed_open_items.indices, [...Array(8).keys(), ...Array.from({length: 8}, (_, i) => 24 + i)]);
    assert.equal(result.lanes.items.indices.length, limit === null ? 32 : limit);
    assert.equal(result.fields.terminal_closure_proof, undefined);
    assert.deepEqual(rows, before);
  }
});

test("recent completion orders true microsecond instants and ignores later edits", () => {
  const rows = [done({completed_at: "2026-01-01T10:00:00.000001+08:00", updated_at: "2026-12-01T00:00:00Z"}),
    done({completed_at: "2026-01-01T02:00:00.000002Z"}), done({completed_at: "invalid"})];
  const result = projectTodoSummary(request(rows));
  assert.deepEqual(result.lanes.recent_completed_advancement_items.indices, [1, 0]);
  assert.equal(result.fields.advancement_done_count, 3);
  assert.equal(result.lanes.items.indices.length, 3);
});

test("equal instants retain reverse source coordinate and stable ties", () => {
  const rows = [done({completed_at: "2026-01-01T10:00:00+08:00", completion_index: 2}),
    done({completed_at: "2026-01-01T02:00:00Z", completion_index: 4}),
    done({completed_at: "2026-01-01T02:00:00Z", completion_index: 4})];
  assert.deepEqual(projectTodoSummary(request(rows)).lanes.recent_completed_advancement_items.indices, [1, 2, 0]);
});

test("selection cannot turn partial source knowledge into a closure proof", () => {
  const select = {role: "agent", status: null, todo_id: null, agent_id: null};
  const full = projectTodoSummary(request([done()], {selection: select}));
  assert.ok(full.fields.terminal_closure_proof);
  const partial = projectTodoSummary(request([done()], {selection: select, full_selection: false}));
  assert.equal(partial.full_selection, false);
  assert.equal(partial.fields.source_proof, undefined);
  assert.equal(partial.fields.terminal_closure_proof, undefined);
  const filtered = projectTodoSummary(request([done(), row()], {selection: {...select, status: "done"}}));
  assert.equal(filtered.fields.terminal_closure_proof, undefined);
  assert.deepEqual(filtered.source_indices, [0]);
});

test("scope preserves original ordinals and closure uses only the selected graph decisions", () => {
  const rows = [row({todo_id: "peer", claimed: true, claim: "other"}),
    done({todo_id: "own", claimed: true, claim: "me"})];
  const result = projectTodoSummary(request(rows, {selection: {role: "agent", status: null, todo_id: null, agent_id: "me"}}));
  assert.deepEqual(result.source_indices, [1]);
  assert.deepEqual(result.lanes.items.indices, [1]);
  assert.equal(result.fields.done_count, 1);
  assert.equal(result.fields.terminal_closure_proof, undefined);
});

test("invalid source or budgets fail closed rather than hiding rows", () => {
  for (const fields of [{item_limit: -1}, {item_limit: 1.5}, {item_limit: true}, {full_selection: null}]) {
    assert.throws(() => projectTodoSummary(request([row()], fields)));
  }
  for (const fields of [{claimed: true}, {claim: "agent"}, {done: true}, {completed_at: 2},
    {has_resume: true}, {successor_gap: "false"}, {handoff_state: "unrecognized"}]) {
    assert.throws(() => projectTodoSummary(request([row(fields)])));
  }
});

test("large native and imported corpora preserve source coverage across every display cap", () => {
  for (const format of ["native", "legacy"] as const) {
    const fixture = productionScaleCoordinationFixture("summary-source", format);
    const records = fixture.projection.todos as JsonObject[];
    const rows = records.map((todo, ordinal) => row({status: todo.status, done: todo.done,
      task_class: todo.task_class, sort: [1, ordinal, "", ""], todo_id: todo.todo_id,
      claim: todo.claimed_by ?? null, claimed: Boolean(todo.claimed_by)}));
    const full = projectTodoSummary(request(rows, {item_limit: null}));
    assert.equal(full.fields.total_count, records.length);
    assert.equal(full.lanes.items.indices.length, records.length);
    for (const limit of [0, 1, 12]) {
      const limited = projectTodoSummary(request(rows, {item_limit: limit}));
      assert.deepEqual(limited.fields, full.fields);
      assert.equal(limited.lanes.items.indices.length, limit);
      for (const lane of Object.values(limited.lanes)) {
        assert.equal(new Set(lane.indices).size, lane.indices.length);
        assert.ok(lane.indices.every(index => index >= 0 && index < records.length));
      }
    }
  }
});
