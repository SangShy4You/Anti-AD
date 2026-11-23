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

    def prepare_partitioned_filter(self, root):
        config = self.prepare(root)
        config["sources"][0]["force_policy"] = None
        config["filter_partitions"] = {"ads.list": [
            {"output": "ads-allow-first.list", "name": "necessary-first", "kind": "preserve", "allowed_policies": ["direct"]},
            {"output": "ads-reject-main.list", "name": "advertising", "kind": "reject", "allowed_policies": ["reject"]},
            {"output": "ads-allow-last.list", "name": "necessary-last", "kind": "preserve", "allowed_policies": ["direct"]},
        ]}
        self.bodies[self.filters] = (b"host,safe.example.com,direct\n"
                                     b"host-suffix,example.com,reject\n"
                                     b"host-suffix,other.example,direct\n")
        (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
        return config

    def test_partitioned_import_forces_only_reject_and_preserves_legacy_mixed_resource(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            self.prepare_partitioned_filter(root)
            self.build(root)
            prefix = root / "rules/quantumultx"
            legacy = (prefix / "ads.list").read_text(encoding="utf-8")
            self.assertIn("host, safe.example.com, direct", legacy)
            self.assertIn("host-suffix, example.com, reject", legacy)
            imports = (prefix / "import.snippet").read_text(encoding="utf-8")
            rows = [line for line in imports.splitlines() if "/ads-" in line]
            self.assertEqual(len(rows), 3)
            self.assertIn("ads-allow-first.list", rows[0])
            self.assertNotIn("force-policy", rows[0])
            self.assertIn("ads-reject-main.list", rows[1])
            self.assertIn("force-policy=reject", rows[1])
            self.assertIn("ads-allow-last.list", rows[2])
            self.assertNotIn("force-policy", rows[2])
            self.assertNotIn("/ads.list,", imports)
            report = json.loads((prefix / "manifest.json").read_bytes())
            partitions = report["filter_partitions"]["ads.list"]
            self.assertTrue(partitions["active_rule_rows_preserved_exactly"])
            self.assertEqual(partitions["output_rules"], 3)
            snapshot = self.snapshot(root)
            self.assertEqual(self.build(root)["changed_files"], [])
            self.assertEqual(snapshot, self.snapshot(root))

    def test_partition_drift_stops_before_any_product_or_manifest_is_published(self):
        with tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
            root = Path(directory)
            self.prepare_partitioned_filter(root)
            self.build(root)
            snapshot = self.snapshot(root)
            self.bodies[self.filters] += b"host,unexpected.other.example,reject\n"
            with self.assertRaisesRegex(ValueError, "topology changed"):
                self.build(root)
            self.assertEqual(snapshot, self.snapshot(root))
            self.bodies[self.filters] = (b"host,safe.example.com,unreviewed\n"
                                         b"host-suffix,example.com,reject\n"
                                         b"host-suffix,other.example,direct\n")
            with self.assertRaisesRegex(ValueError, "policy changed"):
                self.build(root)
            self.assertEqual(snapshot, self.snapshot(root))

    def test_partition_collision_and_non_filter_source_do_not_publish(self):
        for invalid in ("collision", "non-filter"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
                root = Path(directory)
                config = self.prepare_partitioned_filter(root)
                self.build(root)
                snapshot = self.snapshot(root)
                if invalid == "collision":
                    config["filter_partitions"]["ads.list"][0]["output"] = "ads.list"
                    message = "collides"
                else:
                    config["filter_partitions"]["ads.conf"] = config["filter_partitions"].pop("ads.list")
                    message = "not a compiled filter"
                (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    self.build(root)
                self.assertEqual(snapshot, self.snapshot(root))

    def test_rewrite_imports_follow_reviewed_dedup_order_and_keep_optional_resources(self):
        for explicit_order in (True, False):
            with self.subTest(explicit_order=explicit_order), tempfile.TemporaryDirectory(prefix=".test-update-", dir=qx_build.ROOT) as directory:
                root = Path(directory)
                config = self.prepare(root)
                priority_url = "https://raw.githubusercontent.com/example/r/main/priority.conf"
                optional_url = "https://raw.githubusercontent.com/example/r/main/optional.conf"
                config["sources"] += [{"id": "priority", "name": "priority", "url": priority_url},
                                      {"id": "optional", "name": "optional", "url": optional_url}]
                config["products"]["priority.conf"] = {"kind": "rewrite", "sources": ["priority"], "name": "priority"}
                config["products"]["optional.conf"] = {"kind": "rewrite", "sources": ["optional"], "name": "optional", "default_enabled": False}
                shared = self.bodies[self.rewrites]
                self.bodies[self.rewrites] = shared + b"^https://ads-only.example.com/ad url reject\n"
                self.bodies[priority_url] = shared + b"^https://priority.example.com/ad url reject\n"
                self.bodies[optional_url] = b"^https://optional.example.com/ad url reject\n"
                if explicit_order:
                    config["profile_rewrite_order"] = ["priority.conf", "ads.conf"]
                (root / "config/qx-sources.json").write_text(json.dumps(config), encoding="utf-8")
                self.build(root)
                prefix = root / "rules/quantumultx"
                rewrite_rows = (prefix / "import.snippet").read_text(encoding="utf-8").split("[rewrite_remote]\n", 1)[1].splitlines()
                filenames = [line.split(",", 1)[0].rsplit("/", 1)[1] for line in rewrite_rows]
                expected = ["priority.conf", "ads.conf", "optional.conf"] if explicit_order else ["ads.conf", "priority.conf", "optional.conf"]
                self.assertEqual(filenames, expected)
                self.assertIn("enabled=false", rewrite_rows[-1])
                self.assertIn(self.pinned_script, (prefix / "priority.conf").read_text(encoding="utf-8"))
                ads_text = (prefix / "ads.conf").read_text(encoding="utf-8")
                manifest = json.loads((prefix / "manifest.json").read_bytes())
                if explicit_order:
                    self.assertNotIn(self.pinned_script, ads_text)
                    self.assertIn("ads-only.example.com", ads_text)
                    self.assertEqual([entry["file"] for entry in manifest["profile_rewrite_deduplication"]], ["priority.conf", "ads.conf"])
                    self.assertEqual(manifest["profile_rewrite_deduplication"][1]["duplicates_removed"], 1)
                else:
                    self.assertIn(self.pinned_script, ads_text)
                    self.assertEqual(manifest["profile_rewrite_deduplication"], [])

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
