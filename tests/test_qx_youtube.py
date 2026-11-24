"""Offline regression evidence for the reviewed YouTube response pipeline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from scripts.qx_rewrites import compile_rewrites
from scripts.qx_youtube import NATIVE_PATTERN, NATIVE_SOURCE, RESPONSE_SCRIPT, prepare_response_script


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/maasea-youtube-response-65075cdb.js"
PINNED = "https://raw.githubusercontent.com/Maasea/sgmodule/65075cdb388fc5e3094afd7e7314c67b243f3525/Script/Youtube/youtube.response.js"
FIXTURE_SHA256 = "eb924df3fb729480dbf0a05288ea3652dbfd60635f10ce196b303b6caa3d2686"


class YouTubeResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = FIXTURE.read_text(encoding="utf-8")

    def test_provenance_guard_preserves_entire_reviewed_upstream_logic(self):
        self.assertEqual(hashlib.sha256(self.body.encode()).hexdigest(), FIXTURE_SHA256)
        result, report = prepare_response_script(self.body, PINNED)
        self.assertTrue(result.endswith(self.body))
        self.assertTrue(report["source_logic_unchanged"])
        self.assertTrue(report["response_only"])
        self.assertFalse(report["external_worker_imported"])
        self.assertIn("Apache-2.0", result[:300])
        self.assertEqual(report["source_sha256"], FIXTURE_SHA256)

    def test_source_drift_and_forwarding_cannot_silently_replace_background_support(self):
        changed = [
            self.body.replace("backgroundAbility:{active:!0}", "backgroundAbility:{active:!1}", 1),
            self.body.replace("function Br(l,e){Ni(l),Si(l),Pi(l,e)}", "function Br(l,e){Ni(l),Pi(l,e)}", 1),
            self.body.replace('n.bodyBytes=G.transferBodyBytes(r,"ArrayBuffer"):n[i]=r;$done(n)',
                              'n.bodyBytes=r:n[i]=r;$done(n)', 1),
            self.body + '\nconst workerUrl="https://example.workers.dev/";',
            "<html>upstream error</html>",
            "",
        ]
        for body in changed:
            with self.subTest(body=body[-150:]), self.assertRaises(ValueError):
                prepare_response_script(body, PINNED)
        for url in (RESPONSE_SCRIPT, PINNED.replace("Maasea/sgmodule", "other/sgmodule")):
            with self.subTest(url=url), self.assertRaises(ValueError):
                prepare_response_script(self.body, url)

    def test_native_resource_has_one_response_processor_with_player_and_settings(self):
        body = (ROOT / "config/qx-youtube-player.conf").read_text(encoding="utf-8")
        _, report = compile_rewrites([{"id": "youtube_background", "url": NATIVE_SOURCE}],
                                     {"youtube_background": body})
        self.assertEqual(report["script_urls"], [RESPONSE_SCRIPT])
        self.assertEqual(len(report["rules"]), 1)
        self.assertNotIn("script-request", body)
        self.assertNotIn("workers.dev", body)
        matcher = re.compile(NATIVE_PATTERN)
        for endpoint in ("browse", "next", "player", "get_watch", "account/get_setting", "search"):
            for query in ("", "?prettyPrint=false"):
                self.assertTrue(matcher.fullmatch("https://youtubei.googleapis.com/youtubei/v1/" + endpoint + query))
        self.assertFalse(matcher.fullmatch("https://other.example/youtubei/v1/player"))

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for the offline binary-response regression")
    def test_real_reviewed_bundle_handles_quanx_binary_players_without_network(self):
        # Execute the actual audited bundle, with no process/fs/network inside
        # the VM. Fixture protobuf encoding/decoding is independent of its code.
        prepared, _ = prepare_response_script(self.body, PINNED)
        with tempfile.TemporaryDirectory(prefix="qx-youtube-") as directory:
            script = Path(directory) / "youtube-background.js"
            script.write_text(prepared, encoding="utf-8")
            result = subprocess.run(
                [shutil.which("node"), str(ROOT / "tests/fixtures/run_youtube_response.cjs"), str(script)],
                capture_output=True, text=True, check=True, timeout=10,
            )
        evidence = json.loads(result.stdout)
        self.assertIn("player ads/background/PiP", evidence["passed"])
        self.assertIn("QuanX ArrayBuffer callback", evidence["passed"])
        self.assertIn("nested get_watch player", evidence["passed"])


if __name__ == "__main__":
    unittest.main()
