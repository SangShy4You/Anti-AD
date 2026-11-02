"""Ordered ad-guard compilation and optional real Mihomo routing checks."""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from scripts import advanced


def fragment(stages):
    lines = ["# Generated test fragment", "rule-providers:"]
    for number, (policy, rows) in enumerate(stages, 1):
        lines.extend([f"  personal_stage_{number:02d}:", "    type: inline",
                      "    behavior: classical", "    payload:"])
        lines.extend("      - " + json.dumps(row) for row in rows)
    lines.append("rules:")
    lines.extend("  - " + json.dumps(f"RULE-SET,personal_stage_{number:02d},{policy}")
                 for number, (policy, _) in enumerate(stages, 1))
    return ("\n".join(lines) + "\n").encode()


FIXTURE = [
    ("REJECT", ["DOMAIN-SUFFIX,ads.example", "DOMAIN,exact.example", "DOMAIN-KEYWORD,analytics",
                "DOMAIN-WILDCARD,*.children.example",
                "IP-CIDR,203.0.113.0/24"]),
    ("全球加速", ["DOMAIN,keep.ads.example", "DOMAIN,pass.block.example", "DOMAIN-KEYWORD,keep"]),
    ("REJECT", ["DOMAIN-SUFFIX,block.example", "IP-CIDR,198.51.100.0/24,no-resolve"]),
]


def yaml_payload(path):
    return {json.loads(line.strip()[2:]) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- ")}


class AdvancedTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(advanced.__file__).resolve().parents[1]
        self.temp = tempfile.TemporaryDirectory(prefix=".test-update-advanced-", dir=workspace)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "rules").mkdir()
        (self.root / "data").mkdir()
        self.source = self.root / advanced.SOURCE
        self.source.write_bytes(fragment(FIXTURE))
        for name in ("ads-domain.mrs", "ads-ip.mrs"):
            (self.root / "rules" / name).write_bytes(b"unchanged aggregate MRS")

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file()}

    def test_ordered_guard_preserves_stage_membership_and_no_resolve(self):
        result = advanced.build_advanced(self.root)
        metadata = result["metadata"]
        self.assertEqual([s["action"] for s in metadata["stages"]], ["REJECT", "PASS", "REJECT"])
        self.assertEqual(metadata["counts"], {"stages": 3, "mrs_sources": 5, "extra_rows": 3})
        self.assertEqual(yaml_payload(self.root / "rules/advanced/stage-01-domain.yaml"),
                         {"+.ads.example", "exact.example"})
        self.assertEqual(yaml_payload(self.root / "rules/advanced/stage-02-domain.yaml"),
                         {"keep.ads.example", "pass.block.example"})
        merge = (self.root / advanced.MERGE).read_text(encoding="utf-8")
        self.assertIn('"RULE-SET,personal_ads_s03_ip_no_resolve,REJECT,no-resolve"', merge)
        self.assertIn('"SUB-RULE,(OR,((NETWORK,tcp),(NETWORK,udp))),personal_ads"', merge)
        self.assertIn('"classical"', merge)
        self.assertIn('"text"', merge)
        self.assertIn('"./rules/advanced/stage-01-extra.txt"', merge)
        extra = (self.root / "rules/advanced/stage-01-extra.txt").read_text(encoding="utf-8")
        self.assertIn("DOMAIN-KEYWORD,analytics\n", extra)
        self.assertNotIn("DOMAIN-KEYWORD,analytics", merge)
        self.assertNotIn("DOMAIN-SUFFIX,analytics", merge)
        routes = [json.loads(line.strip()[2:]) for line in merge.splitlines()
                  if line.startswith("    - ")]
        self.assertEqual([r.split(",")[1].split("_")[2] for r in routes[:-1]],
                         ["s01", "s01", "s01", "s02", "s02", "s03", "s03"])
        self.assertEqual(routes[-1], "MATCH,PASS")
        for name in ("ads-domain.mrs", "ads-ip.mrs"):
            self.assertEqual((self.root / "rules" / name).read_bytes(), b"unchanged aggregate MRS")
        before = self.snapshot()
        self.assertFalse(advanced.build_advanced(self.root)["changed"])
        self.assertEqual(self.snapshot(), before)

    def test_invalid_source_or_unrepresentable_options_preserve_generated_files(self):
        advanced.build_advanced(self.root)
        for raw in (b"rule-providers:\n  arbitrary: invalid\n",
                    fragment([("REJECT", ["IP-CIDR,203.0.113.0/24,force-cellular"])]),
                    fragment([("REJECT", ["DOMAIN,ads.example,no-resolve"])])):
            with self.subTest(raw=raw):
                self.source.write_bytes(raw)
                before = self.snapshot()
                with self.assertRaises(advanced.AdvancedError):
                    advanced.build_advanced(self.root)
                self.assertEqual(self.snapshot(), before)

    def test_removed_stage_cleanup_refuses_to_delete_edited_files(self):
        advanced.build_advanced(self.root)
        obsolete = self.root / "rules/advanced/stage-03-domain.yaml"
        obsolete.write_text("user-edited generated file", encoding="utf-8")
        self.source.write_bytes(fragment(FIXTURE[:2]))
        before = self.snapshot()
        with self.assertRaises(advanced.AdvancedError):
            advanced.build_advanced(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_removed_stage_cleans_its_generated_remote_extra(self):
        advanced.build_advanced(self.root)
        obsolete = self.root / "rules/advanced/stage-02-extra.txt"
        self.assertTrue(obsolete.is_file())
        self.source.write_bytes(fragment(FIXTURE[:1]))
        result = advanced.build_advanced(self.root)
        self.assertFalse(obsolete.exists())
        self.assertIn("rules/advanced/stage-02-extra.txt", result["written"])
        self.assertTrue((self.root / "rules/advanced/stage-01-extra.txt").is_file())

    def test_public_base_url_rejects_embedded_secrets(self):
        for url in ("https://user:token@example.com/rules", "https://example.com/rules?token=secret"):
            with self.subTest(url=url), self.assertRaises(advanced.AdvancedError):
                advanced.build_advanced(self.root, url)


@unittest.skipUnless(os.environ.get("MIHOMO_TEST_BINARY"), "Set MIHOMO_TEST_BINARY for the real-core routing check")
class NativeAdvancedTests(unittest.TestCase):
    """Use a local origin only; no game, external DNS, airport or credentials."""

    setUp = AdvancedTests.setUp

    def test_native_sub_rule_pass_and_earlier_reject(self):
        tool = Path(os.environ["MIHOMO_TEST_BINARY"]).resolve(strict=True)
        version = subprocess.run([str(tool), "-v"], capture_output=True, text=True,
                                 encoding="utf-8", timeout=10, check=True)
        self.assertIn("Mihomo Meta v1.19.33 ", version.stdout)
        result = advanced.build_advanced(self.root)
        for source in result["metadata"]["mrs_sources"]:
            subprocess.run([str(tool), "convert-ruleset", source["behavior"], "yaml",
                            str(self.root / source["yaml_path"]), str(self.root / source["mrs_path"])],
                           capture_output=True, timeout=30, check=True)

        received = []
        class Origin(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get("Host"))
                body = b"native-adguard-origin"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        self.addCleanup(origin.server_close)
        origin_thread = threading.Thread(target=origin.serve_forever, daemon=True)
        origin_thread.start()
        self.addCleanup(origin.shutdown)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            proxy_port = probe.getsockname()[1]
        hosts = ["keep.ads.example", "pass.block.example", "plain.example", "analytics.example", "other.block.example",
                 "children.example", "one.children.example", "deep.one.children.example"]
        config = (self.root / advanced.MERGE).read_text(encoding="utf-8")
        config += '  - "MATCH,DIRECT"\n'
        config += f'mixed-port: {proxy_port}\nbind-address: "127.0.0.1"\nallow-lan: false\nlog-level: debug\n'
        config += 'dns:\n  enable: true\n  nameserver:\n    - "127.0.0.1:9"\n  use-hosts: true\n'
        config += "hosts:\n" + "".join(f'  "{h}": "127.0.0.1"\n' for h in hosts)
        config_path = self.root / "native-config.yaml"
        config_path.write_text(config, encoding="utf-8")
        checked = subprocess.run([str(tool), "-d", str(self.root), "-f", str(config_path), "-t"],
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        with (self.root / "native-core.log").open("wb") as log:
            process = subprocess.Popen([str(tool), "-d", str(self.root), "-f", str(config_path)],
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        self.fail("Native core exited before opening its listener")
                    try:
                        with socket.create_connection(("127.0.0.1", proxy_port), timeout=0.1):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            self.fail("Native core did not open its listener")
                        time.sleep(0.05)

                def request(host):
                    connection = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=3)
                    try:
                        connection.request("GET", f"http://{host}:{origin.server_port}/")
                        response = connection.getresponse()
                        return response.status, response.read()
                    except (OSError, http.client.HTTPException):
                        return None, b""
                    finally:
                        connection.close()

                for host in ("pass.block.example", "plain.example", "children.example"):
                    self.assertEqual(request(host), (200, b"native-adguard-origin"), host)
                for host in ("keep.ads.example", "analytics.example", "other.block.example",
                             "one.children.example", "deep.one.children.example"):
                    self.assertNotEqual(request(host)[0], 200, host)
                self.assertEqual(set(received), {f"pass.block.example:{origin.server_port}",
                                                 f"plain.example:{origin.server_port}",
                                                 f"children.example:{origin.server_port}"})
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
