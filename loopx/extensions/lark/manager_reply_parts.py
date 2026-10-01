"""Bounded multi-message delivery for a manager answer that does not fit once.

A persisted manager answer that the provider rejects for length used to be left
on the channel as nothing at all. This module owns the alternative: split the
already-validated body into ordered parts, send the parts the provider has not
accepted yet, and record that progress in the same durable delivery state the
single-message path uses, so a retry resumes instead of re-sending.

The counter is not the whole record. A part is counted only after the transport
accepted it, so a state that already shows every part accepted means the reader
has the whole answer even when the caller never got to write its own receipt
(a failed settle write, or a process that stopped right after the last part).
That case settles from the record instead of re-sending nothing forever.

A send the provider accepted but did not read back leaves its provider locator
in the same record. The next attempt verifies that locator before sending the
part again, so an ambiguous send is reconciled instead of repeated.

A partly delivered answer also has to look partly delivered: once the sequence
has stopped mid-answer three times, one bounded notice tells the reader how much
went out and where the rest is. That notice records and verifies its own
locator the same way, so a reader is never told the same thing twice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .inbox_reply import (
    MESSAGE_ID_PATTERN,
    reply_lark_event_inbox,
    verify_lark_inbox_reply,
)
from .outbound import DEFAULT_LARK_TEXT_LIMIT, split_lark_outbound_text

# An oversized answer is delivered as a bounded sequence rather than a flood:
# past this many parts the answer keeps its leading parts and ends with a note
# naming where the full text is already saved.
MANAGER_REPLY_MAX_PARTS = 8
MANAGER_REPLY_OVERFLOW_NOTE = (
    "本条答复超过可投递长度，上面已按顺序发送前面的部分；"
    "完整答复保存在 LoopX 管家会话中。"
)
PART_DELIVERY_COMPLETE_KEY = "delivery_parts_complete"
PART_DELIVERY_VERIFIED_KEY = "delivery_parts_verified"
PART_ATTEMPT_KEY = "delivery_part_attempt"
PART_STALL_NOTICE_KEY = "delivery_part_stall_notice"
PART_STALL_COUNT_KEY = "delivery_part_stall_count"
PART_STALL_NOTICE_ATTEMPT_KEY = "delivery_part_stall_notice_attempt"
PART_DELIVERY_INCOMPLETE = "reply_part_delivery_incomplete"
PART_DELIVERY_COMPLETION_UNVERIFIED = "reply_part_delivery_completion_unverified"
# The notice is a last resort, not the outcome: the sequence counts the attempts
# that stopped the answer mid-sequence (progress does not reset that count, only
# a different split does) and only speaks after three of them, so a transient
# provider hiccup never turns into a message the reader did not need.
PART_STALL_NOTICE_MIN_STALLS = 3
MANAGER_REPLY_STALL_NOTICE = (
    "本条答复超过可发送长度，目前只发出了前面的 {sent}/{count} 段；"
    "完整答复保存在 LoopX 管家会话中，剩余分段会继续重试。"
)


def plan_manager_reply_parts(reply_text: str) -> tuple[list[str], bool]:
    """Return the parts to deliver and whether the remainder was replaced."""

    parts = split_lark_outbound_text(
        reply_text,
        limit=DEFAULT_LARK_TEXT_LIMIT,
        max_parts=MANAGER_REPLY_MAX_PARTS,
        overflow_note=MANAGER_REPLY_OVERFLOW_NOTE,
    )
    truncated = len(parts) == MANAGER_REPLY_MAX_PARTS and (
        MANAGER_REPLY_OVERFLOW_NOTE in parts[-1]
    )
    return parts, truncated


def _reply_verified(reply: Mapping[str, Any]) -> bool:
    """Whether the provider reported this reply present on the channel.

    A reply can be confirmed either by the readback that follows its own send or
    by the reconciliation of an earlier send the provider accepted but did not
    read back. Both mean the reader has that text, which is the fact the record
    keeps; a reconciled send has no new write of its own.
    """

    return bool(
        reply.get("verification_performed") is True
        and reply.get("reply_verified") is True
    )


def _reply_on_channel(reply: Mapping[str, Any]) -> bool:
    """Whether the reader may already have this reply's text.

    ``ok`` also requires the source reaction cleanup to have finished, so a
    reply the provider already accepted can come back not-ok with a cleanup
    still pending. Treating that as delivered is what keeps a retry from sending
    the reader the same text twice, and the pending cleanup stays the
    transport's own business.
    """

    return reply.get("ok") is True or _reply_verified(reply)


def _part_accepted(reply: Mapping[str, Any]) -> bool:
    """Whether this part may be counted as delivered."""

    return _reply_on_channel(reply)


def _accepted_reply_facts(reply: Mapping[str, Any]) -> dict[str, Any]:
    """The durable facts of one part the provider confirmed."""

    return {
        "reply_idempotency_key": reply.get("idempotency_key"),
        PART_DELIVERY_VERIFIED_KEY: _reply_verified(reply),
    }


def completed_part_delivery_receipt(
    delivery_state: Mapping[str, Any],
) -> dict[str, Any] | None:
    """The verified receipt for a sequence whose every part was accepted.

    Returns ``None`` unless the durable record proves both that the sequence
    finished and that the provider verified the last part, so a caller never
    marks a delivery verified on the strength of an unfinished or unverified
    record.
    """

    if delivery_state.get(PART_DELIVERY_COMPLETE_KEY) is not True:
        return None
    if delivery_state.get(PART_DELIVERY_VERIFIED_KEY) is not True:
        return None
    key = delivery_state.get("reply_idempotency_key")
    if not isinstance(key, str) or not key.startswith("sha256:"):
        return None
    return {
        "ok": True,
        "status": "sent_verified",
        "idempotency_key": key,
        "content_format": "text",
        "external_write_performed": True,
        "verification_performed": True,
        "reply_verified": True,
        "part_delivery_reused": True,
    }


def part_delivery_incomplete_reason(delivery_state: Mapping[str, Any]) -> str:
    """Name why a sequence stopped, when the record already says all parts went.

    A recorded counter that reached the part count without a verified
    completion cannot be re-sent (the parts are already on the channel) and
    cannot be settled either, so it gets its own reason instead of the generic
    incomplete one.
    """

    recorded = delivery_state.get("delivery_part_count")
    sent = delivery_state.get("delivery_parts_sent")
    if (
        isinstance(recorded, int)
        and not isinstance(recorded, bool)
        and isinstance(sent, int)
        and not isinstance(sent, bool)
        and recorded > 0
        and sent == recorded
    ):
        return PART_DELIVERY_COMPLETION_UNVERIFIED
    return PART_DELIVERY_INCOMPLETE


def _recorded_attempt(recorded: Any) -> Mapping[str, Any] | None:
    """The provider locator inside one recorded attempt, when it is well formed."""

    if not isinstance(recorded, Mapping):
        return None
    attempt = recorded.get("attempt")
    return attempt if isinstance(attempt, Mapping) else None


def recorded_part_attempt(
    delivery_state: Mapping[str, Any], index: int
) -> Mapping[str, Any] | None:
    """The provider locator of the part that was attempted but not confirmed."""

    recorded = delivery_state.get(PART_ATTEMPT_KEY)
    if not isinstance(recorded, Mapping) or recorded.get("index") != index:
        return None
    return _recorded_attempt(recorded)


def attempt_provider_locator(attempt: Mapping[str, Any]) -> str | None:
    """The message id a recorded attempt can be verified against, when it has one.

    A send the provider accepted without reporting a message id records its
    intent instead of a locator. That record still proves a write happened, and
    ``None`` here is what tells the sequence to stop instead of posting the same
    text a second time.
    """

    message_ref = str(attempt.get("message_ref") or "").strip()
    return message_ref if MESSAGE_ID_PATTERN.fullmatch(message_ref) else None


def _locator_unavailable_result(*, reconciled_key: str) -> dict[str, Any]:
    """The typed outcome for an attempt no readback can key on."""

    return {
        "ok": False,
        "status": "sent_unverified",
        "idempotency_key": None,
        "external_write_performed": True,
        "verification_performed": False,
        "reply_verified": False,
        "blocker": "lark_inbox_reply_not_verified",
        reconciled_key: False,
        "part_locator_unavailable": True,
    }


def recorded_stall_notice_attempt(
    delivery_state: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """The provider locator of a stall notice that was sent but not confirmed."""

    return _recorded_attempt(delivery_state.get(PART_STALL_NOTICE_ATTEMPT_KEY))


def reconciled_part_reply(
    *,
    parts: list[str],
    index: int,
    delivery_state: Mapping[str, Any],
    reply_runner: Any,
    root: Path,
    config_path: Path,
    message_id: str,
) -> Mapping[str, Any] | None:
    """Confirm a previously attempted part instead of sending it twice.

    Returns the verification result when the provider still reports the part on
    the channel, and ``None`` when there is nothing to reconcile or the provider
    could not confirm it (the caller then sends the part, as before). The
    verification performs no write of its own.
    """

    attempt = recorded_part_attempt(delivery_state, index)
    if attempt is None:
        return None
    if attempt_provider_locator(attempt) is None:
        # The provider took the write and gave no message id, so this part cannot
        # be read back. Sending it again risks delivering the same text twice,
        # which is worse than reporting the sequence as unverified: the record
        # keeps the part where it stopped until the caller decides.
        return _locator_unavailable_result(reconciled_key="part_reconciled")
    verified = verify_lark_inbox_reply(
        project=root,
        config_path=config_path,
        message_id=message_id,
        text=parts[index],
        attempt=attempt,
        runner=reply_runner,
    )
    if verified.get("reply_verified") is not True:
        return None
    return {**dict(verified), "part_reconciled": True}


def reconciled_stall_notice(
    *,
    notice: str,
    delivery_state: Mapping[str, Any],
    reply_runner: Any,
    root: Path,
    config_path: Path,
    message_id: str,
) -> Mapping[str, Any] | None:
    """Confirm a previously sent stall notice instead of posting it twice.

    The provider can accept the notice and still fail the readback that proves
    it, and this sequence keeps retrying until the remaining parts go through.
    The recorded locator is what keeps such a notice from being sent again on
    every later attempt, exactly as a part is reconciled before it is re-sent.
    """

    attempt = recorded_stall_notice_attempt(delivery_state)
    if attempt is None:
        return None
    if attempt_provider_locator(attempt) is None:
        return _locator_unavailable_result(reconciled_key="notice_reconciled")
    verified = verify_lark_inbox_reply(
        project=root,
        config_path=config_path,
        message_id=message_id,
        text=notice,
        attempt=attempt,
        runner=reply_runner,
    )
    if verified.get("reply_verified") is not True:
        return None
    return {**dict(verified), "notice_reconciled": True}


def plan_stalled_part_notice(delivery_state: Mapping[str, Any]) -> str | None:
    """The bounded notice a stalled sequence posts once, after real retries.

    A reader who received the first parts of an over-limit answer currently
    learns nothing more: the overflow note that says where the full answer lives
    only travels with the last part, and the remaining parts are retried in the
    background. This notice states what was delivered and where the rest is, and
    it waits for three stalled attempts so an ordinary hiccup stays quiet.
    """

    if delivery_state.get(PART_STALL_NOTICE_KEY) is True:
        return None
    stalls = delivery_state.get(PART_STALL_COUNT_KEY)
    if (
        not isinstance(stalls, int)
        or isinstance(stalls, bool)
        or stalls < PART_STALL_NOTICE_MIN_STALLS
    ):
        return None
    sent = delivery_state.get("delivery_parts_sent")
    count = delivery_state.get("delivery_part_count")
    for value in (sent, count):
        if not isinstance(value, int) or isinstance(value, bool):
            return None
    if not 0 < sent < count:
        return None
    return MANAGER_REPLY_STALL_NOTICE.format(sent=sent, count=count)


def deliver_stall_notice(
    *,
    delivery_state: dict[str, Any],
    delivery_path: Path,
    write_delivery,
    reply_runner: Any,
    root: Path,
    config_path: Path,
    message_id: str,
) -> Mapping[str, Any] | None:
    """Post the once-per-sequence stall notice, confirming a prior send first.

    Returns the transport result of the send or reconciliation, and ``None``
    when this sequence has nothing to tell the reader.
    """

    notice = plan_stalled_part_notice(delivery_state)
    if notice is None:
        return None
    reconciled = reconciled_stall_notice(
        notice=notice,
        delivery_state=delivery_state,
        reply_runner=reply_runner,
        root=root,
        config_path=config_path,
        message_id=message_id,
    )
    if reconciled is not None:
        if reconciled.get("notice_reconciled") is not True:
            # The provider accepted this notice and nothing can read it back, so
            # this record is the only evidence the reader may already have it.
            # Dropping it here would let the next retry post the same notice
            # again; a confirmed notice, below, is the case that settles it.
            return reconciled
        # A confirmed notice is settled: the stall flag carries that fact from
        # here on, so the attempt that proved it is no longer needed.
        delivery_state.pop(PART_STALL_NOTICE_ATTEMPT_KEY, None)
        return reconciled
    # The locator of the send being attempted now replaces any older one, so the
    # record always points at the most recent unconfirmed notice. This runs only
    # on the path that is about to call the provider, where the old record is
    # genuinely superseded.
    delivery_state.pop(PART_STALL_NOTICE_ATTEMPT_KEY, None)

    def record_attempt(attempt: Mapping[str, Any]) -> None:
        # The locator has to survive the attempt that produced it: a retry
        # reloads the record and verifies it instead of posting the notice again.
        delivery_state[PART_STALL_NOTICE_ATTEMPT_KEY] = {"attempt": dict(attempt)}
        delivery_state["updated_at"] = datetime.now(timezone.utc).isoformat()
        write_delivery(delivery_path, delivery_state)

    return reply_lark_event_inbox(
        project=root,
        config_path=config_path,
        message_id=message_id,
        text=notice,
        content_format="text",
        execute=True,
        runner=reply_runner,
        delivery_attempt_recorder=record_attempt,
    )


def deliver_manager_reply_parts(
    *,
    parts: list[str],
    delivery_state: dict[str, Any],
    delivery_path: Path,
    write_delivery,
    reply_runner: Any,
    root: Path,
    config_path: Path,
    message_id: str,
    content_format: str,
) -> Mapping[str, Any] | None:
    """Send the remaining parts in order, resuming from the recorded count.

    The durable state, not the return value, is the record of what the provider
    accepted: each accepted part advances `delivery_parts_sent` before the next
    send, and a rejected part stops the sequence there.
    """

    recorded_count = delivery_state.get("delivery_part_count")
    sent = delivery_state.get("delivery_parts_sent")
    if (
        not isinstance(recorded_count, int)
        or isinstance(recorded_count, bool)
        or recorded_count != len(parts)
        or not isinstance(sent, int)
        or isinstance(sent, bool)
        or not 0 <= sent <= len(parts)
    ):
        # A different split than the one on record cannot be resumed safely.
        sent = 0
        # The stall count describes this sequence's retries, so it goes with the
        # split that produced them instead of counting toward a different one.
        delivery_state.pop(PART_STALL_COUNT_KEY, None)
    elif sent == len(parts):
        # Every part is already on the channel. Settle from the recorded
        # acceptance instead of reporting an incomplete sequence that no retry
        # could ever finish (re-sending would duplicate the whole answer).
        return completed_part_delivery_receipt(delivery_state)
    delivery_state.update(
        delivery_part_count=len(parts),
        delivery_parts_sent=sent,
        format_degraded=True,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    # A sequence that is still being sent is not a complete one, even when a
    # previous attempt recorded a verified completion for a different split.
    delivery_state[PART_DELIVERY_COMPLETE_KEY] = False
    write_delivery(delivery_path, delivery_state)
    last: Mapping[str, Any] | None = None
    for index in range(sent, len(parts)):
        last = reconciled_part_reply(
            parts=parts,
            index=index,
            delivery_state=delivery_state,
            reply_runner=reply_runner,
            root=root,
            config_path=config_path,
            message_id=message_id,
        )
        if last is None:
            # The locator of the part being sent now replaces any older one, so
            # the record always points at the most recent unconfirmed attempt.
            delivery_state.pop(PART_ATTEMPT_KEY, None)

            def record_attempt(attempt: Mapping[str, Any], *, index=index) -> None:
                delivery_state[PART_ATTEMPT_KEY] = {
                    "index": index,
                    "attempt": dict(attempt),
                }
                delivery_state["updated_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                write_delivery(delivery_path, delivery_state)

            last = reply_lark_event_inbox(
                project=root,
                config_path=config_path,
                message_id=message_id,
                text=parts[index],
                content_format=content_format,
                execute=True,
                runner=reply_runner,
                delivery_attempt_recorder=record_attempt,
                # Part delivery is the fallback for a body the provider itself
                # cannot take; a part is never cut by the notification length.
                short_message_limit=None,
            )
        if not _part_accepted(last):
            delivery_state.update(
                delivery_parts_sent=index,
                last_delivery_status=str(last.get("status") or "reply_failed"),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            write_delivery(delivery_path, delivery_state)
            return None
        delivery_state.pop(PART_ATTEMPT_KEY, None)
        delivery_state.update(
            delivery_parts_sent=index + 1,
            **(
                {PART_DELIVERY_COMPLETE_KEY: True, **_accepted_reply_facts(last)}
                if index + 1 == len(parts)
                else _accepted_reply_facts(last)
            ),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        write_delivery(delivery_path, delivery_state)
    return last


def deliver_manager_reply_after_length_failure(
    *,
    reply_text: str,
    delivery_state: dict[str, Any],
    delivery_path: Path,
    write_delivery,
    reply_runner: Any,
    root: Path,
    config_path: Path,
    message_id: str,
) -> tuple[Mapping[str, Any] | None, str | None]:
    """Deliver one over-limit manager answer as bounded parts.

    Returns the last accepted reply, or ``None`` plus the reason to report when
    a part was rejected. A sequence that stops with parts still unsent also tells
    the reader what went out, once, after enough failed attempts. Plain text is
    the only format a split can promise, so the caller has already degraded
    presentation before calling this.
    """

    parts, truncated = plan_manager_reply_parts(reply_text)
    if truncated:
        delivery_state.update(
            delivery_truncated=True,
            delivery_source_char_count=len(reply_text),
        )
    reply = deliver_manager_reply_parts(
        parts=parts,
        delivery_state=delivery_state,
        delivery_path=delivery_path,
        write_delivery=write_delivery,
        reply_runner=reply_runner,
        root=root,
        config_path=config_path,
        message_id=message_id,
        content_format="text",
    )
    if reply is not None:
        return reply, None
    # The answer is only partly on the channel. Tell the reader once, after the
    # sequence has already failed more than one attempt, instead of leaving the
    # delivered parts looking like the whole answer.
    delivery_state[PART_STALL_COUNT_KEY] = (
        int(delivery_state.get(PART_STALL_COUNT_KEY) or 0) + 1
    )
    spoken = deliver_stall_notice(
        delivery_state=delivery_state,
        delivery_path=delivery_path,
        write_delivery=write_delivery,
        reply_runner=reply_runner,
        root=root,
        config_path=config_path,
        message_id=message_id,
    )
    if spoken is not None:
        if _reply_on_channel(spoken):
            delivery_state[PART_STALL_NOTICE_KEY] = True
        delivery_state["last_delivery_notice_status"] = str(
            spoken.get("status") or "reply_failed"
        )
    # The stall count has to survive this attempt either way. A retry reloads the
    # record from disk, so an unwritten increment would restart at zero and the
    # notice would never be reached no matter how often the sequence stalled.
    delivery_state["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_delivery(delivery_path, delivery_state)
    return None, part_delivery_incomplete_reason(delivery_state)


def manager_part_delivery_pending_result(
    *,
    reason: str,
    delivery_state: Mapping[str, Any],
    goal_id: str,
    inbox_config_ref: str,
) -> dict[str, Any]:
    """The typed pending result for a part sequence the provider interrupted."""

    return {
        "ok": False,
        "status": "reply_delivery_pending",
        "reason": reason,
        "delivery_part_count": delivery_state.get("delivery_part_count"),
        "delivery_parts_sent": delivery_state.get("delivery_parts_sent"),
        "delivery_notice_sent": delivery_state.get(PART_STALL_NOTICE_KEY) is True,
        "format_degraded": True,
        "goal_id": goal_id,
        "inbox_config_ref": inbox_config_ref,
        "source_acknowledged": False,
    }


def manager_part_delivery_readback(delivery_state: Mapping[str, Any]) -> dict[str, Any]:
    """Part accounting for a delivered answer, empty when it was one message."""

    if not (
        isinstance(delivery_state.get("delivery_part_count"), int)
        and isinstance(delivery_state.get("delivery_parts_sent"), int)
    ):
        return {}
    return {
        "delivery_part_count": delivery_state["delivery_part_count"],
        "delivery_parts_sent": delivery_state["delivery_parts_sent"],
        "delivery_truncated": bool(delivery_state.get("delivery_truncated")),
    }
