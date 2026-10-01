# Replan history decision owner

Goal/source: overall roadmap #4574, typed control-plane T3 consumer ownership.
The observed gap was independent Python history scans with different retry,
ACK, neutral-accounting and lane semantics. The delivered boundary is one typed history projection (inline or snapshot
transport), with in-process reuse of the existing Todo resume planner. Python keeps legacy codecs and public obligation rendering;
its replaced historical trigger scans and duplicated neutral vocabulary are removed.

Four independently specified regression cases failed on baseline `709734cd6`:
periodic retry overcount, Monitor retry overcount, accepted ACK not resetting
progress repetition, and neutral accounting breaking equivalent progress. The
new owner corrects them while retaining thresholds, precedence and obligation
identity. Typed negative cases and the 280-row multi-agent interleaving fixture
cover scope-before-ACK, retries, missing identities, invalid input and source
immutability. Real File/SQLite consumer tests delete the display before reading
status and invoking quota, rather than substituting an in-memory store.

A read-only local-source rehearsal covered 345 active Todos, 600 history rows
and five agent lanes: all five historical projections matched baseline; isolated
File/SQLite readback and public quota CLI passed without changing the source.
This was an active read-model snapshot, not whole-Goal promotion. Complete source
capture independently rejected an archived dependency with missing/incompatible
role/task-class facts. That migration hold remains and was not bypassed or repaired
in active state.

This closes the history-trigger decision family, not all T3 or default adoption.
Progress fingerprint codecs, obligation assembly, frontier settlement and broader
capture/provider qualification retain their owners. No new model observer,
provider selection, frontend configuration or optional capability is introduced.

## Long-history transport correction

The earlier 600-row rehearsal did not qualify long-lived Goals. Although prose
was excluded, serializing every compact fact in one RPC still grew with history
and blocked `refresh-state` before writeback. A 12,000-retry counterexample fails
on the old boundary; evidence older than the retry flood must still participate.

Placement: the existing built-in work-item replan owner is sufficient; no new
capability, provider, store or optional activation is introduced. The Python
codec chooses transport by serialized byte size only. The local IO adapter checks
an absolute, same-user private regular file, exact length and SHA-256 before
calling the unchanged TS reducer. Small requests preserve the original method;
large ones use a compact snapshot reference. Temporary files survive runtime
retries and are removed on normal success or failure. Abrupt process termination
can leave an OS-temporary orphan; it grants no receipt or authority and is never
reused as canonical state. The same-UID runtime is the existing trust boundary,
not a remote upload service or a new privilege boundary.

Acceptance includes evidence beyond the wire limit, inline/snapshot parity for
all four operations, ACK/peer/retry semantics, digest/size/missing/symlink/input
rejection, private-file cleanup, and real CLI dry-run/writeback/replay followed
by one quota debit. Existing records are preserved byte-for-byte. The response,
trigger identity and 2 MiB RPC limit do not change. CLI is the affected entry;
frontend and Lark require no new setting or projection because they consume the
same unchanged result and errors through existing entrypoints.

This closes the demonstrated transport failure, not all fleet-scale work.
Encoding, parsing and evaluation still use O(history) memory/time. The next S7/R7
capacity slice should measure bridge bytes, peak memory and p95 settlement cost,
then qualify checkpoint/cursor reduction against this complete-history oracle,
including late ACKs, missing attribution and deduplicated Turns. Do not archive,
truncate or increase thresholds merely to make settlement succeed.
