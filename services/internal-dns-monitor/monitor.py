#!/usr/bin/env python3
"""Internal DNS monitor: configuration and probes for an IX LAN client."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import socket
import struct
import sys
from typing import Mapping
from urllib import error, request

DEFAULT_TOKEN_FILE = "/srv/ix/llm-services/runtime/server02/secrets/leto_ops_ingress_token"


def load_env_file(path: Path) -> dict[str, str]:
    """Read a deliberately small KEY=VALUE file; it is not shell-evaluated."""
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"invalid configuration line: {raw_line!r}")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _resolvers_from_resolv_conf(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "nameserver":
            values.append(fields[1])
    return tuple(values)


def _positive_int(value: str, default: int) -> int:
    try:
        return max(1, int(value))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    resolver_servers: tuple[str, ...]
    expected_resolvers: tuple[str, ...]
    pihole_servers: tuple[str, ...]
    observation_ingress_url: str
    token_file: Path
    execution_host: str
    vantage: str
    check_domain: str
    block_domain: str
    fresh_recursion_name: str
    ops_health_url: str
    contingency_failure_threshold: int
    state_file: Path


def load_settings(values: Mapping[str, str], resolv_conf_text: str | None = None) -> Settings:
    if resolv_conf_text is None:
        resolv_conf_text = Path("/etc/resolv.conf").read_text(encoding="utf-8")
    resolver_servers = _csv(values.get("RESOLVER_SERVERS", "")) or _resolvers_from_resolv_conf(resolv_conf_text)
    return Settings(
        resolver_servers=resolver_servers,
        expected_resolvers=_csv(values.get("EXPECTED_RESOLVERS", "")),
        pihole_servers=_csv(values.get("PIHOLE_SERVERS", "")),
        observation_ingress_url=values.get("OBSERVATION_INGRESS_URL", "").strip(),
        token_file=Path(values.get("OPS_TOKEN_FILE", DEFAULT_TOKEN_FILE)),
        execution_host=values.get("EXECUTION_HOST", socket.gethostname()).strip() or socket.gethostname(),
        vantage=values.get("VANTAGE", "ordinary-lan-client").strip() or "ordinary-lan-client",
        check_domain=values.get("CHECK_DOMAIN", "example.com").strip(),
        block_domain=values.get("BLOCK_DOMAIN", "use-application-dns.net").strip(),
        fresh_recursion_name=values.get("FRESH_RECURSION_SUFFIX", values.get("FRESH_RECURSION_NAME", "")).strip(),
        ops_health_url=values.get("OPS_HEALTH_URL", "").strip(),
        contingency_failure_threshold=_positive_int(values.get("CONTINGENCY_FAILURE_THRESHOLD", "3"), 3),
        state_file=Path(values.get("STATE_FILE", "/var/lib/internal-dns-monitor/state.json")),
    )


def _blocked(result: Mapping[str, object]) -> bool:
    if bool(result.get("blocked")) or result.get("rcode") in {"NXDOMAIN", "REFUSED"}:
        return True
    addresses = result.get("answers", [])
    return result.get("rcode") == "NOERROR" and (not addresses or set(addresses).issubset({"0.0.0.0", "::"}))


def collect_observation(settings: Settings, dns_query, http_probe) -> dict:
    """Collect client-side DNS and operations-plane observations.

    Midway is intentionally never a DNS target: IX clients may only observe its
    recursion indirectly through an explicitly configured Pi-hole.
    """
    resolver_path = [
        {"server": server, "udp": dns_query(server, "udp", settings.check_domain)}
        for server in settings.resolver_servers
    ]
    pihole = []
    for server in settings.pihole_servers:
        udp = dns_query(server, "udp", settings.check_domain)
        tcp = dns_query(server, "tcp", settings.check_domain)
        block_udp = dns_query(server, "udp", settings.block_domain)
        block_tcp = dns_query(server, "tcp", settings.block_domain)
        pihole.append(
            {
                "server": server,
                "udp": udp,
                "tcp": tcp,
                "blocking": {"udp": _blocked(block_udp), "tcp": _blocked(block_tcp)},
            }
        )
    fresh_results = []
    if settings.fresh_recursion_name:
        fresh_name = f"{secrets.token_hex(8)}.{settings.fresh_recursion_name.rstrip('.')}"
        fresh_results = [
            {"server": server, "result": dns_query(server, "udp", fresh_name)}
            for server in settings.pihole_servers
        ]
    operations_plane = http_probe(settings.ops_health_url) if settings.ops_health_url else {"ok": None, "skipped": True}
    return {
        "resolver_path": resolver_path,
        "resolver_selection": {
            "configured": list(settings.resolver_servers),
            "expected": list(settings.expected_resolvers),
            "matches_expected": bool(settings.resolver_servers)
            and set(settings.resolver_servers).issubset(settings.expected_resolvers),
        },
        "pihole": pihole,
        "fresh_recursion": {
            "mode": "indirect-via-pihole",
            "direct_midway_attempted": False,
            "applicable": bool(settings.fresh_recursion_name and settings.pihole_servers),
            "results": fresh_results,
        },
        "operations_plane": operations_plane,
    }


def _ok(result: Mapping[str, object]) -> bool:
    return result.get("ok") is True


def observation_is_healthy(observation: Mapping[str, object]) -> bool:
    if not observation.get("resolver_selection", {}).get("matches_expected"):
        return False
    resolver_path = observation.get("resolver_path", [])
    if not resolver_path or not all(_ok(item.get("udp", {})) for item in resolver_path):
        return False
    piholes = observation.get("pihole", [])
    if not piholes or not all(
        _ok(item.get("udp", {}))
        and _ok(item.get("tcp", {}))
        and item.get("blocking", {}).get("udp") is True
        and item.get("blocking", {}).get("tcp") is True
        for item in piholes
    ):
        return False
    fresh = observation.get("fresh_recursion", {})
    if fresh.get("applicable") and not all(_ok(item.get("result", {})) for item in fresh.get("results", [])):
        return False
    operations = observation.get("operations_plane", {})
    return operations.get("ok") is True or operations.get("skipped") is True


def _read_state(state_file: Path) -> dict:
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_state(state_file: Path, state: Mapping[str, object]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_file.with_suffix(state_file.suffix + ".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    temporary.replace(state_file)


def _compact(observation: Mapping[str, object], healthy: bool, contingency: Mapping[str, object]) -> dict:
    return {
        "service": "internal-dns-monitor",
        "healthy": healthy,
        "resolver_selection": observation.get("resolver_selection", {}).get("matches_expected"),
        "resolver_path": [
            {"server": item.get("server"), "udp": _ok(item.get("udp", {}))}
            for item in observation.get("resolver_path", [])
        ],
        "pihole": [
            {
                "server": item.get("server"),
                "udp": _ok(item.get("udp", {})),
                "tcp": _ok(item.get("tcp", {})),
                "block_udp": item.get("blocking", {}).get("udp"),
                "block_tcp": item.get("blocking", {}).get("tcp"),
            }
            for item in observation.get("pihole", [])
        ],
        "fresh_recursion": {
            "mode": observation.get("fresh_recursion", {}).get("mode", "indirect-via-pihole"),
            "applicable": observation.get("fresh_recursion", {}).get("applicable"),
            "ok": all(_ok(item.get("result", {})) for item in observation.get("fresh_recursion", {}).get("results", [])),
        },
        "operations_plane": observation.get("operations_plane", {}).get("ok"),
        "contingency": contingency,
    }


def _pihole_healthy(item: Mapping[str, object]) -> bool:
    return (
        _ok(item.get("udp", {}))
        and _ok(item.get("tcp", {}))
        and item.get("blocking", {}).get("udp") is True
        and item.get("blocking", {}).get("tcp") is True
    )


def _correlation_payload(settings: Settings, observation: Mapping[str, object], sequence: int) -> dict:
    """Map IX-only probe detail into the small cross-vantage observation contract."""
    resolver_path = observation.get("resolver_path", [])
    client_path = bool(observation.get("resolver_selection", {}).get("matches_expected")) and bool(resolver_path) and all(
        _ok(item.get("udp", {})) for item in resolver_path
    )
    piholes = observation.get("pihole", [])
    pihole_status = [_pihole_healthy(item) for item in piholes]
    return {
        "contract_version": "1.0",
        "source": "internal-dns-monitor",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sequence": sequence,
        "execution": {"host": settings.execution_host, "vantage": settings.vantage},
        "checks": {
            "client_path": client_path,
            "resolvers": {
                "pihole_a": pihole_status[0] if len(pihole_status) > 0 else False,
                "pihole_b": pihole_status[1] if len(pihole_status) > 1 else False,
            },
        },
    }


def dispatch_observation(settings: Settings, observation: Mapping[str, object], state_file: Path, post) -> dict:
    """Persist local health context and POST one compact current observation per run."""
    state = _read_state(state_file)
    healthy = observation_is_healthy(observation)
    failures = 0 if healthy else int(state.get("consecutive_failures", 0)) + 1
    contingency = {
        "state": "normal" if healthy else ("armed" if failures >= settings.contingency_failure_threshold else "observing"),
        "consecutive_failures": failures,
    }
    sequence = int(state.get("last_sequence", 0)) + 1
    payload = _correlation_payload(settings, observation, sequence)
    sent = False
    delivery = {"ok": None, "skipped": True}
    if settings.observation_ingress_url and settings.token_file.is_file():
        token = settings.token_file.read_text(encoding="utf-8").strip()
        if token:
            delivery = post(settings.observation_ingress_url, payload, token)
            sent = bool(delivery.get("ok"))
    _write_state(
        state_file,
        {
            "consecutive_failures": failures,
            "last_sequence": sequence,
            "contingency": contingency,
        },
    )
    return {"sent": sent, "delivery": delivery, "contingency": contingency, "healthy": healthy, "payload": payload}


def _dns_name(name: str) -> bytes:
    labels = name.rstrip(".").split(".")
    if not name or any(not label or len(label.encode("idna")) > 63 for label in labels):
        raise ValueError("invalid DNS name")
    return b"".join(bytes([len(label.encode("idna"))]) + label.encode("idna") for label in labels) + b"\0"


def _skip_dns_name(packet: bytes, offset: int) -> int:
    while True:
        if offset >= len(packet):
            raise ValueError("truncated DNS name")
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise ValueError("truncated DNS pointer")
            return offset + 2
        offset += 1
        if length == 0:
            return offset
        offset += length


def _parse_dns_response(packet: bytes, query_id: int) -> dict:
    if len(packet) < 12:
        raise ValueError("short DNS response")
    response_id, flags, questions, answers, _, _ = struct.unpack("!HHHHHH", packet[:12])
    if response_id != query_id or not flags & 0x8000:
        raise ValueError("mismatched DNS response")
    offset = 12
    for _ in range(questions):
        offset = _skip_dns_name(packet, offset) + 4
    addresses: list[str] = []
    for _ in range(answers):
        offset = _skip_dns_name(packet, offset)
        if offset + 10 > len(packet):
            raise ValueError("truncated DNS answer")
        record_type, _, _, length = struct.unpack("!HHIH", packet[offset : offset + 10])
        offset += 10
        data = packet[offset : offset + length]
        if len(data) != length:
            raise ValueError("truncated DNS RDATA")
        if record_type == 1 and length == 4:
            addresses.append(socket.inet_ntop(socket.AF_INET, data))
        elif record_type == 28 and length == 16:
            addresses.append(socket.inet_ntop(socket.AF_INET6, data))
        offset += length
    rcode_number = flags & 0x000F
    rcodes = {0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN", 4: "NOTIMP", 5: "REFUSED"}
    return {"ok": True, "rcode": rcodes.get(rcode_number, f"RCODE{rcode_number}"), "answers": addresses}


def dns_query(server: str, transport: str, name: str, timeout: float = 3.0) -> dict:
    """Issue a single client-side A query over UDP or TCP without dependencies."""
    query_id = secrets.randbits(16)
    packet = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0) + _dns_name(name) + struct.pack("!HH", 1, 1)
    try:
        if transport == "udp":
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                connection.settimeout(timeout)
                connection.sendto(packet, (server, 53))
                response, _ = connection.recvfrom(4096)
        elif transport == "tcp":
            with socket.create_connection((server, 53), timeout=timeout) as connection:
                connection.sendall(struct.pack("!H", len(packet)) + packet)
                size = struct.unpack("!H", _recv_exact(connection, 2))[0]
                response = _recv_exact(connection, size)
        else:
            raise ValueError(f"unsupported DNS transport: {transport}")
        return _parse_dns_response(response, query_id)
    except (OSError, ValueError, struct.error) as exc:
        return {"ok": False, "error": str(exc)[:120]}


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise OSError("unexpected EOF from DNS server")
        data.extend(chunk)
    return bytes(data)


def http_probe(url: str, timeout: float = 5.0) -> dict:
    try:
        with request.urlopen(request.Request(url, headers={"User-Agent": "internal-dns-monitor/1"}), timeout=timeout) as response:
            return {"ok": 200 <= response.status < 400, "status": response.status}
    except (error.URLError, OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)[:120]}


def post_observation(url: str, payload: Mapping[str, object], token: str, timeout: float = 5.0) -> dict:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    message = request.Request(
        url,
        data=data,
        method="POST",
        headers={"X-Leto-Operations-Token": token, "Content-Type": "application/json", "User-Agent": "internal-dns-monitor/1"},
    )
    try:
        with request.urlopen(message, timeout=timeout) as response:
            return {"ok": 200 <= response.status < 300, "status": response.status}
    except error.HTTPError as exc:
        return {"ok": False, "status": exc.code}
    except (error.URLError, OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)[:120]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/etc/internal-dns-monitor/config.env"))
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--check-config", action="store_true", help="parse configuration only; do not probe or report")
    parser.add_argument("--no-report", action="store_true", help="collect only; do not write state or contact ingress")
    arguments = parser.parse_args(argv)
    settings = load_settings(load_env_file(arguments.config))
    if arguments.check_config:
        print(json.dumps({"config": str(arguments.config), "valid": True, "direct_midway_dns": False}))
        return 0
    observation = collect_observation(settings, dns_query=dns_query, http_probe=http_probe)
    if arguments.no_report:
        print(json.dumps(_compact(observation, observation_is_healthy(observation), {"state": "not-recorded"}), separators=(",", ":")))
        return 0
    result = dispatch_observation(settings, observation, arguments.state_file or settings.state_file, post_observation)
    print(json.dumps({"sent": result["sent"], "contingency": result["contingency"], "healthy": result["healthy"]}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
