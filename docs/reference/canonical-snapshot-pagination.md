# Canonical Todo snapshot pagination

After whole-Goal promotion, collection consumers use
`coordination.local_authority.todo_snapshot_page`. Python assembles its pages
into the existing Todo-list result before returning to CLI, status, Turn, Chat,
team planning or projection delivery. Before promotion, the durable writer
fence is absent and the existing legacy path remains unchanged.

## Observable contract

A large, valid canonical collection no longer has to fit in a single RPC
response. Each page contains complete records, up to 4,096 Todo/lease records and
1,792 KiB of UTF-8 JSON. The generic RPC response ceiling remains 2 MiB, leaving 256 KiB for its
envelope. Normal collections can still complete in one page. A record
and its acceptance guard travel together; records are never shortened to meet a
budget. Archived dependency/decision records remain in the full collection.

Todo IDs use the authority codec's deterministic Unicode code-point ordering.
Todos precede leases, with separate offsets and counts. A canonical empty
collection is a complete result; it does not authorize Markdown fallback.
Pagination is a transport mechanism, not a UI display limit or a partial domain
query. Summary computation still receives the complete population.

Each request has `schema_version`, `runtime_root`, `goal_id`, `include_leases`,
`projection_readback` and `after`. The first `after` is null; subsequent calls
send the previous page's `next` unchanged. A continuation contains:

`projection_readback` is the typed confirmation request (`provider_revision`,
`changed`, `attempt`, `target`); it carries the caller's pinned-or-latest intent
and attempt budget, so the page returns one confirmation for the same snapshot
as every page instead of letting the display lock hold a provider commit.

| Field | Meaning |
| --- | --- |
| `snapshot.goal_id` | Goal whose complete collection is being read |
| `snapshot.store_identity` | Provider incarnation; replacing a store invalidates old positions |
| `snapshot.provider_revision`, `snapshot.cursor` | Exact committed authority version |
| `snapshot.query_sha256` | Digest of Goal, lease inclusion and projection-confirmation request |
| `snapshot.todo_count`, `snapshot.lease_count` | Complete populations at that version |
| `todo_offset`, `lease_offset` | Already consumed prefixes within that snapshot |

A page carries the same snapshot, collection metadata, complete `todos`, optional
`leases`, page-local `goal_acceptance_work_guards`, and `next` (null at the end).
Metadata includes the existing read-model declaration, acceptance projection,
handoff mode and requested projection readback. The old direct TS `todo_list`
endpoint remains compatible; the shipped Python collection adapter now uses
pages, and its public result shape stays unchanged.

## Consistency and recovery

The provider is checked again on every page. If a writer commits between pages,
`canonical_snapshot_changed` fails the whole read even when that write happens
to leave Todo data unchanged. Consumers discard every earlier page. The caller
may start a new complete read; the adapter does not silently loop or retry
against a moving head. This also rejects changed queries and store identities.

The Python transport checks page identity, unchanged metadata, count/offset
agreement, progress, record order, duplicates and guard membership. Invalid
transport returns `canonical_snapshot_result_invalid` without partial rows.
The existing TS domain read-model and acceptance owners continue to validate
semantics; Python does not acquire a second Todo rule engine.

A missing local File provider is opened with `existingOnly`; attempting a read
cannot initialize a replacement identity or directory. It still returns the
existing `missing` result, so callers retain the canonical-authority recovery
path instead of treating absence as a new identity error. An existing head with
an unreadable identity remains an identity failure. Selected SQLite and
PostgreSQL profiles retain their existing identity checks and provider failures.
No failure path falls back to a display file.

A single record or metadata envelope that cannot fit is rejected with
`canonical_snapshot_record_too_large` or
`canonical_snapshot_metadata_too_large`. These explicit limits do not qualify
arbitrarily large individual records. Projection confirmation remains tied to
the snapshot read; pending delivery must not trigger a second business mutation.

## Cost and qualification boundary

This implementation bounds **transport responses**, not the whole collection's
memory or provider IO. Each page loads and validates the current provider head;
Python retains the assembled collection. A busy writer may force a caller to
restart. Database cursor streaming or retained read transactions would need a
separate provider lifecycle/cleanup contract and are not implied here.

The budget search measures `Buffer.byteLength(JSON.stringify(page), "utf8")`.
It checks the complete candidate first: removing `next` on a final page can make
the envelope smaller, so byte size is not globally monotone at that last step.
The remaining prefix search retains a continuation and is monotone. Raising the
RPC budget or dropping metadata is not the recovery strategy.

Qualification covers native/imported complex populations, archives, leases,
acceptance guards, overlapping commits, query/incarnation mismatch, malformed
continuations, Unicode ordering and real File/SQLite RPC-to-CLI readback.
The shared authority-store conformance registers the same snapshot tests for
PostgreSQL and other real providers. The real PostgreSQL suite requires an
isolated server/database; a skipped run is not qualification.

This closes the bounded collection-read part of T3/L5. It does not establish D1
permanent projection freshness, SQLite D2 durability/soak, D3 whole-Goal
migration, or default-on qualification. See the
[remaining PR sequence](../architecture/rfcs/shared-goal-authority-state-provider-v0.md).
