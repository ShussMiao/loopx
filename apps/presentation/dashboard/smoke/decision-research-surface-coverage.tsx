import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import type { DecisionResearchView } from "../src/data/decision-research";
import {
  SourcePeriodMetricsCard,
  SpotMarketIdentityCard,
} from "../src/views/decision-research-surface";

type SourcePeriodMetric = DecisionResearchView["source_period_metrics"][number];
type SpotMarketIdentity = NonNullable<DecisionResearchView["spot_market_identity"]>;

const periodMetric: SourcePeriodMetric = {
  metric_id: "synthetic-fees",
  label: "Synthetic fees",
  event_namespace: "synthetic.period.metric",
  event_id: "event-2026w01",
  event_at: "2026-01-07T23:00:00Z",
  instrument_id: "SYNTH-USD",
  scope_id: "synthetic-scope",
  period_start: "2026-01-01",
  period_end: "2026-01-07",
  source_state: "ok",
  value: 125,
  unit: "USD",
  metric_basis: "period_estimate",
  metric_semantics: "generic",
  value_origin: "derived",
  value_precision: "exact",
  observation_authority: "derived_exact",
  sign_basis: "not_signed",
  fee_inclusion: "not_applicable",
  account_scope: "not_applicable",
  account_value_role: "not_applicable",
  includes_isolated_margin: false,
  expected_components: ["core", "secondary"],
  observed_components: ["core"],
  double_counted_components: ["secondary"],
  numerator_scope: ["core"],
  denominator_scope: [],
  lineage_id: "synthetic-upstream-week",
  source_ref: "source:synthetic-fees",
  methodology_state: "verified",
  anomaly_state: "unverified",
  event_identity: {
    namespace: "synthetic.period.metric",
    source_event_id: "event-2026w01",
    event_at: "2026-01-07T23:00:00Z",
    instrument_id: "SYNTH-USD",
    scope_id: "synthetic-scope",
  },
  coverage_state: "partial",
  missing_components: ["secondary"],
  lineage_state: "primary",
  duplicate_of: null,
  independent_evidence: true,
  gap_reasons: ["anomaly:unverified"],
  account_nav_treatment: "not_account_value",
  ready_eligible: false,
  admission_reason: "source_period_metric_is_evidence_only",
};

assert.equal(renderToStaticMarkup(<SourcePeriodMetricsCard metrics={[]} />), "");
const metricsMarkup = renderToStaticMarkup(
  <SourcePeriodMetricsCard
    metrics={[
      periodMetric,
      {
        ...periodMetric,
        metric_id: "synthetic-missing",
        period_start: "2026-01-08",
        period_end: "2026-01-08",
        value: null,
        observed_components: [],
        double_counted_components: [],
        numerator_scope: [],
        denominator_scope: ["capital"],
        coverage_state: "missing",
        independent_evidence: false,
        gap_reasons: [],
      },
    ]}
  />,
);
assert.match(metricsMarkup, /125 USD/);
assert.match(metricsMarkup, /2026-01-01 → 2026-01-07/);
assert.match(metricsMarkup, /missing \(not zero\)/);
assert.match(metricsMarkup, /Excluded double-counted components:.*secondary/);
assert.match(metricsMarkup, /Holds:.*anomaly:unverified/);
assert.match(metricsMarkup, /capital/);

const spotIdentity: SpotMarketIdentity = {
  pairs: [],
  tokens: [],
  contexts: [],
  markets: [
    {
      pair_name: "SYNTH-SPOT",
      context_coin: "SYNTH-SPOT",
      base_asset: { index: 3, symbol: "SYN" },
      quote_asset: { index: 0, symbol: "USDC" },
      observed_at: "2026-01-15T12:00:00Z",
      mark_price: 4.25,
      canonicality: "noncanonical_name",
      backing_inference: "not_inferred",
      source_refs: ["source:pair", "source:base", "source:quote", "source:context"],
      ready_eligible: false,
    },
    {
      pair_name: "MISSING-SPOT",
      context_coin: "MISSING-SPOT",
      base_asset: { index: 4, symbol: "MISS" },
      quote_asset: { index: 0, symbol: "USDC" },
      observed_at: "2026-01-15T12:00:00Z",
      mark_price: null,
      canonicality: "canonical_name",
      backing_inference: "not_inferred",
      source_refs: ["source:pair-2", "source:base-2", "source:quote", "source:context-2"],
      ready_eligible: false,
    },
  ],
};

assert.equal(renderToStaticMarkup(<SpotMarketIdentityCard identity={null} />), "");
assert.equal(
  renderToStaticMarkup(<SpotMarketIdentityCard identity={{ ...spotIdentity, markets: [] }} />),
  "",
);
const spotMarkup = renderToStaticMarkup(
  <SpotMarketIdentityCard identity={spotIdentity} />,
);
assert.match(spotMarkup, /SYN \/ USDC/);
assert.match(spotMarkup, /4.25/);
assert.match(spotMarkup, /missing \(not zero\)/);

console.log("Decision research source-period rendering coverage passed");
