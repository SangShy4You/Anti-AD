from pathlib import Path
import json
import tempfile
import unittest

from scripts import qx_build


class BuildTests(unittest.TestCase):
    def prepare(self, root):
        (root / "config").mkdir()
        (root / "scripts").mkdir()
        for name in ("qx_build.py", "qx_filters.py", "qx_rewrites.py", "qx_dependencies.py"):
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
