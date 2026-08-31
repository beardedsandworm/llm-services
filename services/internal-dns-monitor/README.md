# internal-dns-monitor

A dependency-free Python monitor intended to run on an ordinary IX LAN client. It is source-only: `install.sh` copies files and reloads unit metadata, but intentionally does **not** enable, start, or deploy anything.

## What one run observes

1. **Configured resolver path** — `RESOLVER_SERVERS`, or the client `/etc/resolv.conf` when it is blank.
2. **Expected resolver selection** — every configured resolver must be listed in `EXPECTED_RESOLVERS`.
3. **Direct Pi-hole behavior** — each configured `PIHOLE_SERVERS` endpoint receives A queries over UDP and TCP, plus UDP/TCP queries for `BLOCK_DOMAIN`. A block is recognized as `NXDOMAIN`, `REFUSED`, an empty `NOERROR`, or all-null A/AAAA answers.
4. **Fresh-recursion diagnostic** — if `FRESH_RECURSION_SUFFIX` is set, the monitor prepends a random label and queries it **only through each Pi-hole**. This forces a client/Pi-hole-path lookup while respecting the enforced contract: IX clients never send direct DNS probes to Midway. The observation explicitly records `indirect-via-pihole` and `direct_midway_attempted: false`.
5. **Operations plane** — optional unauthenticated GET to `OPS_HEALTH_URL`.

The monitor POSTs one compact **current** observation per run to the DNS correlation endpoint when `OBSERVATION_INGRESS_URL` is configured. It uses `X-Leto-Operations-Token` Header Auth and consumes the existing centrally materialized `/srv/ix/llm-services/runtime/server02/secrets/leto_ops_ingress_token`; it never logs, copies, encrypts, decrypts, rotates, or owns that token. The payload carries a monotonic local sequence and contains no direct-Midway result.

## Local contingency state

`STATE_FILE` stores only a JSON signature, consecutive-failure counter, and one of `normal`, `observing`, or `armed`. It makes no notification calls, creates no credentials, and provisions no external resources. In particular, it avoids duplicate normal reports. Any future notification path must be explicitly designed and configured separately.

## Configuration

Copy `config.env.example` to `/etc/internal-dns-monitor/config.env` during an approved install and set:

- `EXPECTED_RESOLVERS` and `PIHOLE_SERVERS` to the approved LAN IPs;
- a known policy-blocked `BLOCK_DOMAIN`;
- optional `FRESH_RECURSION_SUFFIX` under a domain for which an NXDOMAIN is acceptable;
- `OPS_HEALTH_URL` and `OBSERVATION_INGRESS_URL` only when their endpoints are approved;

The config parser deliberately supports only plain `KEY=VALUE` lines; it does not evaluate shell expressions. Do not put token material in it.

## Source checks

```bash
./verify.sh
```

This runs the unit tests, parses only the example config, and validates the source unit files. It does not issue DNS requests, POST observations, access the token, install files, enable units, or start services.

## Approved installation procedure

```bash
sudo ./install.sh
# review /etc/internal-dns-monitor/config.env
# separately approved step only:
# sudo systemctl enable --now internal-dns-monitor.timer
```

`install.sh` creates a writable local state directory for the `lightweight` service account, installs the program/config template/units, and performs `systemctl daemon-reload`; it never enables or starts the timer.
