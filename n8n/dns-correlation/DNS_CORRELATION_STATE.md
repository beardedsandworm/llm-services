# DNS correlation/state workflow

## Live identity and route boundary

- Workflow: `Correlate DNS Current Observations`
- n8n workflow ID: `6aOCYolK7VbF4oit`
- Active workflow version: read back through REST after the delivery repair.
- Producer route: `POST https://ops.wormlogic.com/webhook/leto/dns-observations`
- Authentication: existing n8n **Header Auth** credential metadata `Leto Operations — Event Ingress` (`httpHeaderAuth`); neither this source nor either monitor repository contains its value.

External and LAN producers use the normal HTTPS `ops.wormlogic.com` route. The correlation workflow alone calls the co-resident Operational Event Ingress through its supported local listener, `http://127.0.0.1:5678/webhook/leto/events`, using the same Header Auth credential. This avoids making an internal workflow loop through split-horizon DNS or Caddy. No n8n restart is needed for a workflow update.

## Observation contract v1

Each monitor posts one compact current object, not individual DNS probe events:

```json
{
  "contract_version": "1.0",
  "source": "internal-dns-monitor",
  "observed_at": "2026-08-30T12:00:00Z",
  "sequence": 42,
  "execution": {
    "host": "ix-lan-monitor",
    "vantage": "ordinary-lan-client",
    "runtime_revision": "optional-release-revision"
  },
  "checks": {
    "client_path": true,
    "resolvers": { "pihole_a": true, "pihole_b": true }
  }
}
```

External observations use the same envelope but replace `client_path` with `external_path` and add the only permitted direct-Midway result:

```json
{
  "contract_version": "1.0",
  "source": "external-dns-resilience",
  "observed_at": "2026-08-30T12:00:00Z",
  "sequence": 42,
  "execution": { "host": "heighliner", "vantage": "external-wireguard" },
  "checks": {
    "external_path": true,
    "midway_recursion": false,
    "resolvers": { "pihole_a": true, "pihole_b": true }
  }
}
```

**Authority boundary:** ordinary IX/LAN clients are blocked from direct Midway DNS. Therefore an `internal-dns-monitor` payload containing `checks.midway_recursion` is rejected with HTTP 400. Only external direct-path evidence may carry that field. Internal client-path and Pi-hole results corroborate household impact; they do not query Midway directly.

Duplicate or out-of-order sequences for a source return 202 without changing state. Input must contain the exact two recognized sources and boolean check values.

## Bounded state and condition policy

The workflow uses bounded `global` workflow staticData because the Data Tables API is unavailable to this API key (403). It retains at most eight recent observer summaries (48-hour eviction), six condition episodes, 32 delivery-audit entries, 32 acknowledged event IDs, and a bounded set of pending action events. Freshness is six minutes, with a six-minute initial grace period; stale-state evaluation happens when another observation arrives, not from a hidden timer.

Actionable transitions enter the pending set before HTTP delivery. Only the HTTP success branch acknowledges/removes the exact event. Failed calls retain the same event ID and retry on the next accepted current observation; the existing ingress remains the idempotency authority. An open episode without a past acknowledgement is safely backfilled with its deterministic opened event.

Only these canonical conditions are derived:

| Condition | Derivation and promotion policy |
|---|---|
| `dns_service_impact` | Internal ordinary-client path fails and direct Pi-hole evidence is not fully healthy. Promoted on `opened`/`recovered`. |
| `individual_resolver_degradation` | Exactly one internal direct Pi-hole result fails while the internal client path is healthy. Promoted. |
| `lan_resolver_selection_failure` | Internal client path fails while both direct Pi-hole checks are healthy. Promoted. |
| `external_path_impairment` | External path fails while a fresh internal client path is healthy. Promoted. |
| `midway_recursion_instability` | External direct Midway fresh-recursion check fails while client-facing internal evidence is healthy. Stored as diagnostic evidence only; never sent to Operational Event Ingress. |
| `internal_observer_stale` | Fresh LAN-side evidence stops arriving after bootstrap grace. Promoted as loss of corroboration, not as an asserted DNS outage. |

Actionable transition events alone are sent with the existing Header Auth credential to the existing active `POST /webhook/leto/events` Operational Event Ingress. They use deterministic event IDs (`dns-correlation-state:<condition>:<transition>:<episode>`) and that ingress owns incident lifecycle and Alert Routing. This workflow has no Alert Routing node, no reporting node, and does not modify either existing workflow.

## Verified live behavior

- The active REST workflow contains seven nodes, binds Header Auth by credential metadata only, and targets the supported local Operational Event Ingress listener.
- The source JSON parses; the exact Code-node logic passes nine contract/state tests, including retry of a failed actionable opened event with its stable identity.
- Real-vantage tests passed: Heighliner unauthenticated request 403; healthy external/internal current observations 202; and Midway-only open/recovery recorded without an ingress or alert execution.
- The deliberate `external_path_impairment` episode was initially unable to reach ingress through the public hostname. After the local-listener repair, its pending opened event (`dns-correlation-state:external_path_impairment:opened:1`) was accepted by Operational Event Ingress and Alert Routing, then its matching recovered event was accepted for the same incident key and routed.
- Existing Operational Event Ingress, Alert Routing, and the external monitor were not modified. The internal monitor timer remains disabled pending the separate migration decision.
