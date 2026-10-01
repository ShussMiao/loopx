"""Lark card projection for the finance-owned source-period view.

The renderer consumes the same validated ``decision_research_dashboard_v0``
view as the Dashboard. It does not read provider payloads or define a second
finance schema.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from loopx.extensions.lark.presentation.message_card import (
    build_lark_markdown_reply_card,
)

from .presentation_view import validate_decision_research_view


_LARK_MARKDOWN_CONTROL_RE = re.compile(r"([\\`*_{}\[\]!|>~])")


def _lark_plain_text(value: object) -> str:
    """Keep validated display text from changing the surrounding card markup."""

    compact = " ".join(str(value).split())
    return _LARK_MARKDOWN_CONTROL_RE.sub(r"\\\1", compact)


def _display_value(metric: Mapping[str, Any]) -> str:
    value = metric.get("value")
    if value is None:
        return "missing (not zero)"
    if isinstance(value, float):
        return f"{value:g} {metric['unit']}"
    return f"{value} {metric['unit']}"


def render_source_period_metrics_markdown(view: Mapping[str, Any]) -> str:
    """Render a bounded source-period summary from the canonical finance view."""

    validated = validate_decision_research_view(view)
    metrics = validated.get("source_period_metrics", [])
    spot_markets = validated.get("spot_market_identity", {}).get("markets", [])
    if not metrics and not spot_markets:
        return (
            "**Source-period evidence**\n\n"
            "No source-period metrics were projected. Missing evidence is not zero."
        )
    lines = [
        "**Source-period evidence**",
        "",
        "These rows are evidence-only and never grant ready or trading authority.",
    ]
    for metric in metrics:
        period = (
            metric["period_start"]
            if metric["period_start"] == metric["period_end"]
            else f"{metric['period_start']} → {metric['period_end']}"
        )
        lines.extend(
            [
                "",
                f"**{_lark_plain_text(metric['label'])}** · `{period}`",
                f"- Value: {_lark_plain_text(_display_value(metric))} · basis `{metric['metric_basis']}` / `{metric['metric_semantics']}` · {metric['value_origin']} / {metric['value_precision']}",
                f"- Coverage: `{metric['coverage_state']}` · observed {len(metric['observed_components'])}/{len(metric['expected_components'])} · methodology `{metric['methodology_state']}` · anomaly `{metric['anomaly_state']}`",
                f"- Event: `{metric['event_identity']['namespace']}` / `{metric['event_identity']['source_event_id']}` · `{metric['event_identity']['instrument_id']}` · `{metric['event_identity']['event_at']}`",
                f"- Lineage: `{metric['lineage_state']}` · authority `{metric['observation_authority']}` · independent evidence `{str(metric['independent_evidence']).lower()}` · source {_lark_plain_text(metric['source_ref'])}",
                f"- Accounting: sign `{metric['sign_basis']}` · fee `{metric['fee_inclusion']}` · NAV treatment `{metric['account_nav_treatment']}`",
            ]
        )
        if metric["missing_components"]:
            lines.append(
                "- Missing components: "
                + ", ".join(
                    _lark_plain_text(component)
                    for component in metric["missing_components"]
                )
            )
        if metric["double_counted_components"]:
            lines.append(
                "- Excluded double-counted components: "
                + ", ".join(
                    _lark_plain_text(component)
                    for component in metric["double_counted_components"]
                )
            )
        if metric["gap_reasons"]:
            lines.append(
                "- Holds: "
                + ", ".join(
                    _lark_plain_text(reason) for reason in metric["gap_reasons"]
                )
            )
    if spot_markets:
        lines.extend(
            [
                "",
                "**Spot identity joins**",
                "Contexts join by `context.coin == pair.name`; assets resolve by explicit index, never array position.",
            ]
        )
        for market in spot_markets:
            price = (
                "missing (not zero)"
                if market["mark_price"] is None
                else f"{market['mark_price']:g}"
            )
            lines.extend(
                [
                    "",
                    f"**{_lark_plain_text(market['pair_name'])}** · {_lark_plain_text(market['base_asset']['symbol'])} / {_lark_plain_text(market['quote_asset']['symbol'])}",
                    f"- Context: {_lark_plain_text(market['context_coin'])} · observed `{market['observed_at']}` · mark `{price}`",
                    f"- Canonicality: `{market['canonicality']}` · backing `{market['backing_inference']}`",
                ]
            )
    return "\n".join(lines)


def build_source_period_metrics_lark_card(
    view: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a send-ready card without performing an external message write."""

    return build_lark_markdown_reply_card(
        render_source_period_metrics_markdown(view),
        title="Finance source-period evidence",
        template="yellow",
        footer="LoopX finance projection · evidence only · never auto-ready",
    )
