import assert from "node:assert/strict";
import test from "node:test";
import {resolveConversationScope} from "../../loopx/control_plane/collaboration/conversation_scope.ts";

test("owner steward is independent of the selected project; project scope is exact", () => {
  assert.deepEqual(resolveConversationScope({channel_id: "manager", goal_id: "alpha"}),
    {kind: "owner_portfolio", goal_ids: null, private_conversation: true});
  for (const goal of ["alpha", "_alpha", ".alpha", "-alpha"]) {
    assert.deepEqual(resolveConversationScope({channel_id: `goal.${goal}`, goal_id: goal}),
      {kind: "owner_goal", goal_ids: [goal], private_conversation: true});
  }
});

test("a project name, role label or external anchor cannot grant a wider scope", () => {
  for (const input of [
    {channel_id: "goal.beta", goal_id: "alpha"},
    {channel_id: "goal.alpha"},
    {channel_id: "goal.loopx-manager", goal_id: "loopx-manager"},
    {channel_id: "task.alpha", goal_id: "alpha", role: "manager"},
    {channel_id: "manager.external.", goal_id: "alpha"},
    {channel_id: "goal.a/../b", goal_id: "a/../b"},
    {channel_id: "goal..", goal_id: "."},
    {channel_id: "goal...", goal_id: ".."},
    {channel_id: "goal.alpha", goal_id: "alpha", origin: "lark"},
    {channel_id: "goal.alpha", goal_id: "alpha", origin: "unknown"},
  ]) {
    assert.deepEqual(resolveConversationScope(input),
      {kind: "unavailable", goal_ids: [], private_conversation: false});
  }
  assert.deepEqual(resolveConversationScope({channel_id: "manager.external.audience", goal_id: "alpha"}),
    {kind: "external_audience", goal_ids: [], private_conversation: false});
});
