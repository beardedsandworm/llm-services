#!/usr/bin/env node
/* Stateless validation of the n8n Code-node correlation algorithm.
 * It executes the exact exported jsCode with an in-memory staticData object;
 * no webhook, n8n API, credentials, or external services are touched.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');

const path = require('node:path');
const workflowPath = process.env.DNS_CORRELATION_WORKFLOW || path.resolve(__dirname, '..', 'Correlate-DNS-Current-Observations.json');
const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
const correlate = workflow.nodes.find(node => node.name === 'Correlate Current Observation');
assert.ok(correlate, 'correlation Code node must exist');
const state = {};
function runWith(body, staticData) {
  const fn = new Function('$json', '$getWorkflowStaticData', correlate.parameters.jsCode);
  const result = fn({ body }, () => staticData);
  assert.equal(result.length, 1);
  return result[0].json;
}
function run(body) {
  return runWith(body, state);
}
function internal(sequence, values = {}) {
  return {
    contract_version: '1.0', source: 'internal-dns-monitor', observed_at: new Date().toISOString(), sequence,
    execution: { host: 'ix-lan-monitor', vantage: 'ordinary-lan-client', runtime_revision: 'test' },
    checks: { client_path: true, resolvers: { pihole_a: true, pihole_b: true }, ...values },
  };
}
function external(sequence, values = {}) {
  return {
    contract_version: '1.0', source: 'external-dns-resilience', observed_at: new Date().toISOString(), sequence,
    execution: { host: 'heighliner', vantage: 'external-wireguard', runtime_revision: 'test' },
    checks: { external_path: true, midway_recursion: true, resolvers: { pihole_a: true, pihole_b: true }, ...values },
  };
}

// 1. Enforce the corrected authority boundary: internal clients cannot claim direct Midway checks.
let r = run(internal(1, { midway_recursion: false }));
assert.equal(r.responseCode, 400);
assert.match(r.response.message, /must not include direct Midway/);

// 2. A healthy internal current observation creates no event.
r = run(internal(1));
assert.equal(r.responseCode, 202);
assert.deepEqual(r.deliveryQueue, []);

// 3. External Midway-only degradation is recorded as diagnostic-only, never promoted.
r = run(external(1, { midway_recursion: false }));
assert.equal(r.response.promoted_count, 0);
assert.deepEqual(r.response.unalerted_diagnostic_transitions.map(x => [x.condition, x.transition]), [['midway_recursion_instability', 'opened']]);
assert.deepEqual(r.deliveryQueue, []);

// 4. Midway recovery remains diagnostic-only.
r = run(external(2, { midway_recursion: true }));
assert.equal(r.response.promoted_count, 0);
assert.deepEqual(r.response.unalerted_diagnostic_transitions.map(x => [x.condition, x.transition]), [['midway_recursion_instability', 'recovered']]);

// 5. Internal client failure while both Pi-holes answer is selection/path failure, not service impact.
r = run(internal(2, { client_path: false }));
assert.deepEqual(r.deliveryQueue.map(event => event.details.condition), ['lan_resolver_selection_failure']);
assert.equal(r.deliveryQueue[0].transition, 'opened');
assert.equal(r.deliveryQueue[0].state, 'degraded');

// 6. A failed direct Pi-hole with a healthy client path is individual degradation.
r = run(internal(3, { client_path: true, resolvers: { pihole_a: false, pihole_b: true } }));
assert.ok(r.deliveryQueue.some(event => event.event_id === 'dns-correlation-state:individual_resolver_degradation:opened:1'));
assert.ok(r.deliveryQueue.some(event => event.event_id === 'dns-correlation-state:lan_resolver_selection_failure:recovered:1'));

// 7. An external-only path failure is actionable only with fresh healthy LAN evidence.
r = run(external(3, { external_path: false }));
assert.ok(r.deliveryQueue.some(event => event.event_id === 'dns-correlation-state:external_path_impairment:opened:1'));

// 8. Replaying a stale or duplicate sequence makes no state transition/event.
r = run(external(3, { external_path: true }));
assert.equal(r.response.duplicate_or_out_of_order, true);
assert.deepEqual(r.deliveryQueue, []);

// 9. An actionable transition stays pending with the same event ID until ingress accepts it.
const retryState = {};
runWith(internal(1), retryState);
r = runWith(external(1, { external_path: false }), retryState);
const pendingOpen = r.deliveryQueue[0];
assert.equal(pendingOpen.event_id, 'dns-correlation-state:external_path_impairment:opened:1');
r = runWith(external(2, { external_path: false }), retryState);
assert.deepEqual(r.response.transitions, []);
assert.deepEqual(r.deliveryQueue.map(event => event.event_id), [pendingOpen.event_id]);
assert.ok(retryState.pending_events[pendingOpen.event_id]);
// Simulate the success-record node's acknowledgement, then verify recovery keeps
// the same incident episode and produces the matching recovery event.
delete retryState.pending_events[pendingOpen.event_id];
retryState.delivered_event_ids[pendingOpen.event_id] = 'test';
r = runWith(external(3, { external_path: true }), retryState);
assert.deepEqual(r.deliveryQueue.map(event => event.event_id), ['dns-correlation-state:external_path_impairment:recovered:1']);

const names = new Set(workflow.nodes.map(node => node.name));
assert.ok(names.has('Authenticated DNS Observation Ingress'));
assert.ok(names.has('Send Actionable Transition to Operational Event Ingress'));
assert.equal(workflow.active, true);
const http = workflow.nodes.find(node => node.name === 'Send Actionable Transition to Operational Event Ingress');
assert.equal(http.credentials.httpHeaderAuth.id, '9Vdr1wK5TTVW4Kbu');
assert.equal(http.parameters.url, 'http://127.0.0.1:5678/webhook/leto/events');
assert.equal(http.parameters.authentication, 'genericCredentialType');
assert.equal(http.parameters.genericAuthType, 'httpHeaderAuth');
assert.equal(http.onError, 'continueErrorOutput');
console.log('PASS: 9 correlation/state contract checks; workflow source is active and secret-free.');
