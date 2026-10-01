"""Task-adaptive presentation contract for a steward answer.

The readback describes the complete answer's presentation format and length.
It does not infer whether a conclusion is true, whether links were opened, or
whether a cited source is fresh. Those judgments belong to the evidence read.
"""

from __future__ import annotations

MANAGER_ANSWER_CONTRACT_SCHEMA_VERSION = "manager_answer_contract_v1"


def manager_answer_contract_instruction() -> str:
    """Give one adaptive rule to both installed and in-turn steward context."""

    return (
        "Answer the user's actual question at a depth proportionate to the work. "
        "For a simple factual question, give the direct answer and its source without a template. "
        "For an investigation or decision, lead with your judgment, then provide a readable Markdown result with the material comparisons, evidence links or versions, and next decisions the user needs. "
        "Distinguish verified facts, recorded claims and your inferences. State material missing or stale evidence as a bounded limitation after the useful result, never as a substitute for it. "
        "Do not force every answer into fixed sections or shorten a substantive result into an ID inventory. "
        "Use only ordinary Markdown text; never include executable HTML in an answer."
    )


def classify_manager_answer_shape(text: str) -> dict[str, object]:
    """Read back answer presence without duplicating the Markdown parser.

    A short direct answer and a long report are equally present. The UI owns
    Markdown block parsing; this field never scores quality or requires labels.
    """

    return {
        "schema_version": MANAGER_ANSWER_CONTRACT_SCHEMA_VERSION,
        "state": "present",
        "format": "markdown",
        "character_count": len(text),
    }


__all__ = [
    "MANAGER_ANSWER_CONTRACT_SCHEMA_VERSION",
    "classify_manager_answer_shape",
    "manager_answer_contract_instruction",
]
