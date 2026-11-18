// Fixtures for the render-providers UI tests. Contract: docs/test-tree/render-providers.md.
type Json = Record<string, unknown>;

// One entry of GET /batches/<id>/providers.
export function provider(over: Json = {}): Json {
  return {
    id: "local-mac",
    name: "This Mac",
    kind: "local",
    data_rule: "real_allowed",
    setup: { state: "ready", reason: null },
    estimate: { seconds_per_video: 30, batch_seconds: 300, batch_cost_usd: 0 },
    estimate_label: null,
    spend_cap_usd: null,
    spent_usd: 0,
    remaining_usd: null,
    selectable: true,
    refusal: null,
    ...over,
  };
}

// The remote, demo-only provider with a cap; ready and unmeasured unless overridden.
export function modal(over: Json = {}): Json {
  return provider({
    id: "modal-demo",
    name: "Modal (demo)",
    kind: "remote_function",
    data_rule: "demo_only",
    estimate: null,
    estimate_label: "not measured yet",
    spend_cap_usd: 5,
    spent_usd: 0.3,
    remaining_usd: 4.7,
    ...over,
  });
}

// The whole GET /batches/<id>/providers body.
export function providersBody(
  providers: Json[] = [provider()],
  over: Json = {},
): Json {
  return {
    data_class: "real",
    selected_provider_id: null,
    any_selectable: providers.some((p) => p.selectable === true),
    message: null,
    providers,
    ...over,
  };
}
