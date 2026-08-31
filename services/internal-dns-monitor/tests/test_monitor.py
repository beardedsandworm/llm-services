import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from monitor import collect_observation, dispatch_observation, load_env_file, load_settings, main, post_observation  # noqa: E402


class SettingsTests(unittest.TestCase):
    def test_configured_resolver_path_and_expected_selection_are_parsed(self):
        settings = load_settings(
            {
                "RESOLVER_SERVERS": "10.42.42.53, 10.42.42.54",
                "EXPECTED_RESOLVERS": "10.42.42.53",
                "PIHOLE_SERVERS": "10.42.42.53",
                "OBSERVATION_INGRESS_URL": "https://ops.example.invalid/webhook/leto/dns-observations",
            },
            resolv_conf_text="nameserver 127.0.0.53\n",
        )

        self.assertEqual(settings.resolver_servers, ("10.42.42.53", "10.42.42.54"))
        self.assertEqual(settings.expected_resolvers, ("10.42.42.53",))
        self.assertEqual(settings.pihole_servers, ("10.42.42.53",))
        self.assertEqual(settings.observation_ingress_url, "https://ops.example.invalid/webhook/leto/dns-observations")

    def test_env_file_reads_only_key_value_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.env"
            config.write_text("# comment\nRESOLVER_SERVERS=10.42.42.53\nOBSERVATION_INGRESS_URL='https://ops.example.invalid/webhook/leto/dns-observations'\n", encoding="utf-8")
            values = load_env_file(config)

        self.assertEqual(values["RESOLVER_SERVERS"], "10.42.42.53")
        self.assertEqual(values["OBSERVATION_INGRESS_URL"], "https://ops.example.invalid/webhook/leto/dns-observations")


class ObservationTests(unittest.TestCase):
    def test_direct_pihole_probes_and_indirect_fresh_recursion_never_target_midway(self):
        settings = load_settings(
            {
                "RESOLVER_SERVERS": "10.42.42.53",
                "EXPECTED_RESOLVERS": "10.42.42.53",
                "PIHOLE_SERVERS": "10.42.42.53",
                "CHECK_DOMAIN": "example.com",
                "BLOCK_DOMAIN": "blocked.example",
                "FRESH_RECURSION_NAME": "fresh.example",
                "OPS_HEALTH_URL": "https://ops.example.invalid/health",
            },
            resolv_conf_text="",
        )
        calls = []

        def dns_query(server, transport, name):
            calls.append((server, transport, name))
            return {"ok": True, "rcode": "NXDOMAIN" if name == "blocked.example" else "NOERROR"}

        observation = collect_observation(settings, dns_query=dns_query, http_probe=lambda url: {"ok": True})

        self.assertTrue(observation["resolver_selection"]["matches_expected"])
        self.assertEqual(observation["pihole"][0]["udp"]["ok"], True)
        self.assertEqual(observation["pihole"][0]["tcp"]["ok"], True)
        self.assertTrue(observation["pihole"][0]["blocking"]["udp"])
        self.assertEqual(observation["fresh_recursion"]["mode"], "indirect-via-pihole")
        self.assertFalse(observation["fresh_recursion"]["direct_midway_attempted"])
        self.assertTrue(observation["operations_plane"]["ok"])
        self.assertFalse(any(server.lower() == "midway" for server, _, _ in calls))


class ReportingTests(unittest.TestCase):
    def test_authenticated_normal_observation_is_sent_once_and_contingency_stays_local(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token_file = root / "token"
            token_file.write_text("secret-token\n", encoding="utf-8")
            state_file = root / "state.json"
            settings = load_settings(
                {
                    "OBSERVATION_INGRESS_URL": "https://ops.example.invalid/webhook/leto/dns-observations",
                    "OPS_TOKEN_FILE": str(token_file),
                    "CONTINGENCY_FAILURE_THRESHOLD": "2",
                },
                resolv_conf_text="nameserver 10.42.42.53\n",
            )
            observation = {
                "resolver_path": [{"server": "10.42.42.53", "udp": {"ok": True}}],
                "resolver_selection": {"matches_expected": True},
                "pihole": [{"udp": {"ok": True}, "tcp": {"ok": True}, "blocking": {"udp": True, "tcp": True}}],
                "fresh_recursion": {"applicable": False, "results": []},
                "operations_plane": {"ok": True},
            }
            deliveries = []

            def post(url, payload, token):
                deliveries.append((url, payload, token))
                return {"ok": True, "status": 202}

            first = dispatch_observation(settings, observation, state_file, post)
            second = dispatch_observation(settings, observation, state_file, post)

            self.assertTrue(first["sent"])
            self.assertTrue(second["sent"])
            self.assertEqual(len(deliveries), 2)
            self.assertEqual(deliveries[0][2], "secret-token")
            self.assertEqual([item[1]["sequence"] for item in deliveries], [1, 2])
            self.assertEqual(deliveries[0][1]["source"], "internal-dns-monitor")
            self.assertEqual(first["contingency"]["state"], "normal")


class CorrelationContractTests(unittest.TestCase):
    def test_each_current_observation_uses_header_auth_contract_and_monotonic_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token_file = root / "token"
            token_file.write_text("secret-token\n", encoding="utf-8")
            state_file = root / "state.json"
            settings = load_settings(
                {
                    "OBSERVATION_INGRESS_URL": "https://ops.example.invalid/webhook/leto/dns-observations",
                    "OPS_TOKEN_FILE": str(token_file),
                    "EXECUTION_HOST": "ix-test-client",
                    "VANTAGE": "ordinary-lan-client",
                    "PIHOLE_SERVERS": "10.42.42.10,10.42.42.11",
                },
                resolv_conf_text="nameserver 10.42.42.10\n",
            )
            observation = {
                "resolver_path": [{"server": "10.42.42.10", "udp": {"ok": True}}],
                "resolver_selection": {"matches_expected": True},
                "pihole": [
                    {"udp": {"ok": True}, "tcp": {"ok": True}, "blocking": {"udp": True, "tcp": True}},
                    {"udp": {"ok": True}, "tcp": {"ok": True}, "blocking": {"udp": True, "tcp": True}},
                ],
                "fresh_recursion": {"applicable": False, "results": []},
                "operations_plane": {"ok": True},
            }
            deliveries = []

            def post(url, payload, token):
                deliveries.append((url, payload, token))
                return {"ok": True, "status": 202}

            first = dispatch_observation(settings, observation, state_file, post)
            second = dispatch_observation(settings, observation, state_file, post)

        self.assertTrue(first["sent"])
        self.assertTrue(second["sent"])
        self.assertEqual([payload["sequence"] for _, payload, _ in deliveries], [1, 2])
        payload = deliveries[0][1]
        self.assertEqual(payload["contract_version"], "1.0")
        self.assertEqual(payload["source"], "internal-dns-monitor")
        self.assertEqual(payload["execution"], {"host": "ix-test-client", "vantage": "ordinary-lan-client"})
        self.assertEqual(payload["checks"], {"client_path": True, "resolvers": {"pihole_a": True, "pihole_b": True}})
        self.assertNotIn("midway_recursion", payload["checks"])

    def test_post_observation_uses_established_leto_header_auth(self):
        class Response:
            status = 202

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("monitor.request.urlopen", return_value=Response()) as urlopen:
            result = post_observation("https://ops.example.invalid/webhook/leto/dns-observations", {"contract_version": "1.0"}, "secret-token")

        self.assertEqual(result, {"ok": True, "status": 202})
        request_message = urlopen.call_args.args[0]
        self.assertEqual(request_message.get_header("X-leto-operations-token"), "secret-token")
        self.assertIsNone(request_message.get_header("Authorization"))


class MainTests(unittest.TestCase):
    def test_main_returns_success_after_accepted_current_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.env"
            token = root / "token"
            state = root / "state.json"
            token.write_text("secret-token\n", encoding="utf-8")
            config.write_text(
                "\n".join(
                    [
                        "RESOLVER_SERVERS=10.42.42.10,10.42.42.11",
                        "EXPECTED_RESOLVERS=10.42.42.10,10.42.42.11",
                        "PIHOLE_SERVERS=10.42.42.10,10.42.42.11",
                        "OBSERVATION_INGRESS_URL=https://ops.example.invalid/webhook/leto/dns-observations",
                        f"OPS_TOKEN_FILE={token}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            observation = {
                "resolver_path": [{"server": "10.42.42.10", "udp": {"ok": True}}],
                "resolver_selection": {"matches_expected": True},
                "pihole": [
                    {"udp": {"ok": True}, "tcp": {"ok": True}, "blocking": {"udp": True, "tcp": True}},
                    {"udp": {"ok": True}, "tcp": {"ok": True}, "blocking": {"udp": True, "tcp": True}},
                ],
                "fresh_recursion": {"applicable": False, "results": []},
                "operations_plane": {"ok": True},
            }
            output = io.StringIO()
            with patch("monitor.collect_observation", return_value=observation), patch(
                "monitor.post_observation", return_value={"ok": True, "status": 202}
            ), redirect_stdout(output):
                result = main(["--config", str(config), "--state-file", str(state)])

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), {"sent": True, "contingency": {"state": "normal", "consecutive_failures": 0}, "healthy": True})


if __name__ == "__main__":
    unittest.main()
