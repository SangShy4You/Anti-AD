from pathlib import Path
import io
import json
import struct
import tempfile
import unittest
from unittest import mock
import zlib

from scripts import qx_build


class BuildTests(unittest.TestCase):
    def prepare(self, root):
        (root / "config").mkdir()
        (root / "scripts").mkdir()
        for name in qx_build.GENERATOR_MODULES:
            (root / "scripts" / name).write_text("test", encoding="utf-8")
        self.commit = "1" * 40
        self.script = "https://raw.githubusercontent.com/example/r/main/ads.js?mode=AbC#argument"
        self.pinned_script = self.script.replace("/main/", "/" + self.commit + "/")
        self.script_download = self.pinned_script.split("#")[0]
        self.filters = "https://raw.githubusercontent.com/example/r/main/filter.list"
        self.rewrites = "https://raw.githubusercontent.com/example/r/main/rewrite.conf"
        config = {"scope": "ads", "sources": [
            {"id": "f", "name": "filter", "url": self.filters, "force_policy": "reject"},
            {"id": "r", "name": "rewrite", "url": self.rewrites}],
            "products": {
                "ads.list": {"kind": "filter", "sources": ["f"], "name": "ads"},
                "ads.conf": {"kind": "rewrite", "sources": ["r"], "name": "rewrite"}},
            "approved_script_urls": [self.script]}
        (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
        self.bodies = {self.filters: b"host,ads.example.com,reject\n",
                       self.rewrites: (r"^https://api\.example\.com/ads url script-response-body " + self.script +
                                       "\nhostname = api.example.com\n").encode(),
                       self.script_download: b"$done({body:'{}'});"}
        return config

    def build(self, root, **kwargs):
        return qx_build.build(root, fetcher=self.bodies.__getitem__,
                              resolver=kwargs.pop("resolver", lambda _: self.commit), **kwargs)

    def snapshot(self, root):
        return {str(p.relative_to(root)): p.read_bytes() for p in (root / "rules").rglob("*") if p.is_file()}

    def test_deterministic_build_preserves_parameters_and_mixed_policy_import(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            self.prepare(root)
            self.build(root)
            snapshot = self.snapshot(root)
            result = self.build(root)
            self.assertEqual(result["changed_files"], [])
            self.assertEqual(snapshot, self.snapshot(root))
            resource = (root / "rules/quantumultx/ads.conf").read_text(encoding="utf-8")
            self.assertIn(self.pinned_script, resource)
            self.assertNotIn(self.script, resource)
            self.assertIn("?mode=AbC#argument", resource)
            manifest = json.loads((root / "rules/quantumultx/manifest.json").read_bytes())
            self.assertEqual(manifest["script_dependencies"][0]["url"], self.script)
            self.assertEqual(manifest["script_dependencies"][0]["pinned_url"], self.pinned_script)
            self.assertEqual(manifest["script_dependencies"][0]["fetch_url"], self.script_download)
            self.assertNotIn("force-policy", (root / "rules/quantumultx/import.snippet").read_text(encoding="utf-8"))

    def test_dependency_failure_or_new_script_retains_all_published_products(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            config = self.prepare(root)
            self.build(root)
            snapshot = self.snapshot(root)
            self.bodies[self.script_download] = b"<html>Not a script</html>"
            with self.assertRaises(Exception):
                self.build(root)
            self.assertEqual(snapshot, self.snapshot(root))
            config["approved_script_urls"] = []
            (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "need review"):
                self.build(root)
            self.assertEqual(snapshot, self.snapshot(root))

    def test_already_immutable_script_url_does_not_resolve_another_revision(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            config = self.prepare(root)
            config["approved_script_urls"] = [self.pinned_script]
            (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
            self.bodies[self.rewrites] = self.bodies[self.rewrites].replace(
                self.script.encode(), self.pinned_script.encode())

            def unexpected_resolver(key):
                raise AssertionError("immutable dependency attempted ref resolution: " + key)

            self.build(root, resolver=unexpected_resolver)
            resource = (root / "rules/quantumultx/ads.conf").read_text(encoding="utf-8")
            self.assertIn(self.pinned_script, resource)

    def test_minimum_rule_count_failure_preserves_last_good_outputs(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            config = self.prepare(root)
            self.build(root)
            snapshot = self.snapshot(root)
            config["sources"][0]["min_rules"] = 2
            (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "below its reviewed minimum"):
                self.build(root)
            self.assertEqual(snapshot, self.snapshot(root))

    def test_unresolved_local_dependencies_and_mitm_conflicts_preserve_outputs(self):
        invalid = [
            ("local_script_references", "^https://api.example.com/a url script-response-body missing.js"),
            ("local_data_references", "^https://api.example.com/b url echo-response text/html echo-response missing.html"),
            ("hostname_conflicts", "^https://api.example.com/c url reject-dict\n"
                                   "hostname = api.example.com, -api.example.com"),
        ]
        for category, text in invalid:
            with self.subTest(category=category), tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
                root = Path(directory)
                self.prepare(root)
                self.build(root)
                snapshot = self.snapshot(root)
                self.bodies[self.rewrites] = text.encode("utf-8")
                with self.assertRaisesRegex(ValueError, category):
                    self.build(root)
                self.assertEqual(snapshot, self.snapshot(root))

    def test_unmatched_audited_script_patch_never_publishes(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            config = self.prepare(root)
            self.build(root)
            snapshot = self.snapshot(root)
            config["script_patches"] = {self.script: {
                "filename": "reviewed-ads.js", "reason": "fixture patch context",
                "old": "a known obsolete expression", "new": "a reviewed replacement expression",
            }}
            (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed around an audited patch"):
                self.build(root)
            self.assertEqual(snapshot, self.snapshot(root))

    def test_javascript_syntax_failure_preserves_every_last_good_product(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            self.prepare(root)
            self.build(root)
            snapshot = self.snapshot(root)
            # Valid UTF-8 with a familiar proxy API is insufficient: it must parse.
            self.bodies[self.script_download] = b"$done({body: });"
            with self.assertRaisesRegex(ValueError, "JavaScript syntax check failed"):
                self.build(root)
            self.assertEqual(snapshot, self.snapshot(root))

    def test_local_reviewed_filter_uses_config_file_instead_of_fetching_body(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            config = self.prepare(root)
            local = root / "config/reviewed-local.list"
            local.write_text("host,reviewed.example.com,reject\n", encoding="utf-8")
            config["sources"][0]["local_path"] = "config/reviewed-local.list"
            (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
            del self.bodies[self.filters]
            self.build(root)
            output = (root / "rules/quantumultx/ads.list").read_text(encoding="utf-8")
            self.assertIn("reviewed.example.com", output)
            manifest = json.loads((root / "rules/quantumultx/manifest.json").read_bytes())
            filtered = next(s for s in manifest["sources"] if s["id"] == "f")
            self.assertEqual(filtered["sha256"], qx_build.digest(local.read_bytes()))

    def test_invalid_local_paths_cannot_read_outside_config_or_publish(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            config = self.prepare(root)
            self.build(root)
            snapshot = self.snapshot(root)
            (root / "outside.list").write_text("host,outside.example.com,reject\n", encoding="utf-8")
            invalid = ["../outside.list", "outside.list", "config/../outside.list",
                       "config//outside.list", "config/./outside.list", "config/../../outside.list",
                       "config/C:/outside.list", "config\\outside.list", "config/a\n.list"]
            for relative in invalid:
                config["sources"][0]["local_path"] = relative
                (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
                with self.subTest(relative=relative), self.assertRaises(Exception):
                    self.build(root)
                self.assertEqual(snapshot, self.snapshot(root))

    def test_local_config_symlink_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            base = Path(directory)
            root = base / "repo"
            root.mkdir()
            config = self.prepare(root)
            self.build(root)
            snapshot = self.snapshot(root)
            outside = base / "private-outside.list"
            outside.write_text("host,outside.example.com,reject\n", encoding="utf-8")
            link = root / "config/link.list"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("OS does not grant symlink creation")
            config["sources"][0]["local_path"] = "config/link.list"
            (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(qx_build.update.UpdateError, "escapes its root"):
                self.build(root)
            self.assertEqual(snapshot, self.snapshot(root))

    def test_browser_asset_mime_or_script_syntax_failure_preserves_snapshot(self):
        asset = "https://cdn.jsdelivr.net/gh/limbopro/Adblock4limbo@" + "a" * 40 + "/Adguard/Adblock4limbo.user.js"
        cases = [("text/plain", b"console.log('plain');", "JavaScript MIME"),
                 ("application/javascript", b"console.log( ;", "JavaScript syntax")]
        for mime, raw, expected in cases:
            with self.subTest(mime=mime), tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
                root = Path(directory)
                config = self.prepare(root)
                self.build(root)
                snapshot = self.snapshot(root)
                config["script_patches"] = {self.script: {
                    "filename": "limbo-fixture.js", "reason": "fixture browser dependency",
                    "mode": "limbo-browser"}}
                (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
                response = io.BytesIO(raw)
                response.status = 200
                response.headers = {"Content-Type": mime}
                # The real patch's syntax/layout guards are covered elsewhere.
                # Exercise the build transaction after patching has completed.
                with mock.patch.object(qx_build, "patch_limbo_entry", return_value=("$done({});", {"browser_assets": [asset]})), \
                     mock.patch.object(qx_build.urllib.request, "urlopen", return_value=response):
                    with self.assertRaisesRegex(ValueError, expected):
                        self.build(root)
                self.assertEqual(snapshot, self.snapshot(root))

    def test_transparent_png_roundtrips_chunk_crcs_geometry_and_zero_alpha(self):
        raw = qx_build.transparent_png()
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
        position, chunks, pixels = 8, [], b""
        while position < len(raw):
            size = struct.unpack(">I", raw[position:position + 4])[0]
            kind = raw[position + 4:position + 8]
            data = raw[position + 8:position + 8 + size]
            crc = struct.unpack(">I", raw[position + 8 + size:position + 12 + size])[0]
            self.assertEqual(crc, zlib.crc32(kind + data) & 0xffffffff)
            chunks.append(kind)
            if kind == b"IHDR":
                self.assertEqual(struct.unpack(">IIBBBBB", data), (1, 1, 8, 6, 0, 0, 0))
            elif kind == b"IDAT":
                pixels += data
            elif kind == b"IEND":
                self.assertEqual(data, b"")
            position += 12 + size
        self.assertEqual(position, len(raw))
        self.assertEqual(chunks, [b"IHDR", b"IDAT", b"IEND"])
        # Filter byte + red, green, blue, alpha: a transparent 1x1 RGBA pixel.
        self.assertEqual(zlib.decompress(pixels), b"\0\0\0\0\0")

    def test_reviewed_patch_publishes_transparent_asset_and_keeps_url_parameters(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            config = self.prepare(root)
            config["script_patches"] = {self.script: {
                "filename": "patched-fixture.js", "reason": "fixture transparent asset",
                "old": "'{}'", "new": "'{\"ads\":[]}'", "transparent_asset": True}}
            (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
            self.build(root)
            prefix = root / "rules/quantumultx"
            self.assertEqual((prefix / "assets/transparent.png").read_bytes(), qx_build.transparent_png())
            rewrite = (prefix / "ads.conf").read_text(encoding="utf-8")
            self.assertIn("/scripts/patched-fixture.js?mode=AbC#argument", rewrite)
            self.assertIn("'{}'", self.bodies[self.script_download].decode())

    def test_raw_url_canonicalization_never_drops_query_but_strips_download_fragment(self):
        self.assertEqual(qx_build.download_url("https://github.com/o/r/raw/main/a.js?q=1#x"),
                         "https://raw.githubusercontent.com/o/r/main/a.js?q=1")
        self.assertEqual(qx_build.download_url("https://gist.githubusercontent.com/o/id/raw/a.js#x"),
                         "https://gist.githubusercontent.com/o/id/raw/a.js")
        for url in ("http://raw.githubusercontent.com/o/r/main/a.js", "https://example.com/a.js",
                    "https://github.com/o/r/blob/main/a.js", "https://x@y/raw/a.js"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                qx_build.download_url(url)


if __name__ == "__main__":
    unittest.main()
