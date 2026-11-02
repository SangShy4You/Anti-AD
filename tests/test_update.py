from __future__ import annotations

from email.message import Message
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error
import urllib.response

from scripts import update


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def generated_snapshot(root, *, include_mtime=False):
    result = {}
    for folder in ("rules", "data"):
        if (root / folder).exists():
            for path in (root / folder).rglob("*"):
                if path.is_file():
                    value = path.read_bytes()
                    result[path.relative_to(root).as_posix()] = (
                        (value, path.stat().st_mtime_ns) if include_mtime else value)
    return result


def http_response(body, content_type="text/plain", declared_length=None):
    headers = Message()
    headers["Content-Type"] = content_type
    if declared_length is not None:
        headers["Content-Length"] = str(declared_length)
    return urllib.response.addinfourl(io.BytesIO(body), headers,
                                     "https://example.invalid/source", code=200)


class DownloadTests(unittest.TestCase):
    def test_download_reads_and_validates_transport_response(self):
        cases = [
            (b"blocked by gateway", "text/html"),
            (b"<!DOCTYPE html><html>Error</html>", "text/plain"),
            (b"", "text/plain"),
        ]
        with mock.patch.object(update.urllib.request, "urlopen", return_value=http_response(
                b"HOST,ads.example.com,REJECT\n")):
            self.assertEqual(update.fetch_url("https://example.invalid/source", attempts=1),
                             b"HOST,ads.example.com,REJECT\n")
        for body, kind in cases:
            with self.subTest(kind=kind, body=body), mock.patch.object(
                    update.urllib.request, "urlopen", return_value=http_response(body, kind)):
                with self.assertRaises(update.UpdateError):
                    update.fetch_url("https://example.invalid/source", attempts=1)
        # No Content-Length header: this catches silently reading only the limit.
        with mock.patch.object(update.urllib.request, "urlopen",
                               return_value=http_response(b"x" * 65)):
            with self.assertRaises(update.UpdateError):
                update.fetch_url("https://example.invalid/source", attempts=1, limit=64)

    def test_declared_oversize_and_truncated_responses_fail(self):
        for body, declared in ((b"x", 65), (b"short", 50)):
            with self.subTest(declared=declared), mock.patch.object(
                    update.urllib.request, "urlopen",
                    return_value=http_response(body, declared_length=declared)):
                with self.assertRaises(update.UpdateError):
                    update.fetch_url("https://example.invalid/source", attempts=1, limit=64)

    def test_transient_failure_retries_but_404_does_not(self):
        url = "https://example.invalid/source"
        unavailable = urllib.error.HTTPError(url, 503, "unavailable", {}, None)
        with mock.patch.object(update.urllib.request, "urlopen", side_effect=[
                unavailable, http_response(b"HOST,ads.example.com,REJECT\n")]) as opener:
            with mock.patch.object(update.time, "sleep") as sleep:
                self.assertTrue(update.fetch_url(url, attempts=2))
                self.assertEqual(opener.call_count, 2)
                sleep.assert_called_once_with(1)
        missing = urllib.error.HTTPError(url, 404, "missing", {}, None)
        with mock.patch.object(update.urllib.request, "urlopen", side_effect=missing) as opener:
            with mock.patch.object(update.time, "sleep") as sleep:
                with self.assertRaises(update.UpdateError):
                    update.fetch_url(url, attempts=3)
                self.assertEqual(opener.call_count, 1)
                sleep.assert_not_called()

    def test_body_limit_has_no_silent_truncation(self):
        self.assertEqual(update.validate_body(b"abcdefgh", limit=8), "abcdefgh")
        with self.assertRaises(update.UpdateError):
            update.validate_body(b"abcdefghi", limit=8)

    def test_non_http_source_is_rejected(self):
        with self.assertRaises(update.UpdateError):
            update.fetch_url("file:///etc/passwd", attempts=1)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        # Stay inside the workspace on Windows, where the sandbox may deny
        # cross-directory replacement in its redirected system temp folder.
        workspace = Path(update.__file__).resolve().parents[1]
        self.temp = tempfile.TemporaryDirectory(prefix=".test-update-", dir=workspace)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.offline = self.base / "offline"
        self.offline.mkdir()
        self.catalog = {"schema_version": 1, "sources": [
            {"id": "block", "name": "Block", "url": "https://example.invalid/block",
             "role": "block", "enabled": True, "source_format": "mixed",
             "expected_policy": "reject", "original_order": 1},
            {"id": "allow", "name": "Allow", "url": "https://example.invalid/allow",
             "role": "allow", "enabled": True, "source_format": "mixed",
             "expected_policy": "direct", "original_order": 2},
        ], "excluded": []}
        write_json(self.root / "config/upstreams.json", self.catalog)
        write_json(self.root / "config/personal.json", {"disabled_sources": []})
        (self.root / "scripts").mkdir()
        (self.root / "scripts/generator.py").write_text("# generator v1\n", encoding="utf-8")
        (self.offline / "block.txt").write_text(
            "HOST-SUFFIX,ads.example.com,REJECT\nHOST,exact.example.net,REJECT\n"
            "IP-CIDR,203.0.113.0/24,REJECT\n", encoding="utf-8")
        (self.offline / "allow.txt").write_text(
            "HOST,keep.ads.example.com,DIRECT\n", encoding="utf-8")

    def build(self, **kwargs):
        return update.update_repository(self.root, self.offline, **kwargs)

    def change_source(self):
        with (self.offline / "block.txt").open("a", encoding="utf-8") as stream:
            stream.write("HOST,new-ad.example.org,REJECT\n")

    def test_unchanged_update_does_not_compile_or_write(self):
        self.assertTrue(self.build()["changed"])
        before = generated_snapshot(self.root, include_mtime=True)
        def forbidden_compile(*args):
            self.fail("Identical inputs and intact outputs must not compile again")
        result = self.build(compiler=forbidden_compile)
        self.assertEqual(result, {"changed": False, "compiled": False, "written": []})
        self.assertEqual(generated_snapshot(self.root, include_mtime=True), before)

    def test_single_source_failure_preserves_all_existing_outputs(self):
        self.build()
        before = generated_snapshot(self.root, include_mtime=True)
        self.change_source()
        (self.offline / "allow.txt").unlink()
        with self.assertRaises(update.UpdateError):
            self.build()
        self.assertEqual(generated_snapshot(self.root, include_mtime=True), before)

    def test_invalid_compiler_input_preserves_all_existing_outputs(self):
        self.build()
        before = generated_snapshot(self.root, include_mtime=True)
        (self.offline / "block.txt").write_text("UNKNOWN-RULE,garbage\n", encoding="utf-8")
        with self.assertRaises((ValueError, update.UpdateError)):
            self.build()
        self.assertEqual(generated_snapshot(self.root, include_mtime=True), before)

    def test_missing_output_or_generator_change_forces_rebuild(self):
        self.build()
        state = json.loads((self.root / "data/upstream-state.json").read_text(encoding="utf-8"))
        relative = next(path for path in state["outputs"] if path.startswith("rules/"))
        saved = (self.root / relative).read_bytes()
        (self.root / relative).unlink()
        self.assertTrue(self.build()["compiled"])
        self.assertEqual((self.root / relative).read_bytes(), saved)
        (self.root / "scripts/generator.py").write_text("# generator v2\n", encoding="utf-8")
        result = self.build()
        self.assertTrue(result["compiled"])
        self.assertIn("data/upstream-state.json", result["written"])

    def test_raw_hash_and_url_are_recorded_without_a_check_timestamp(self):
        self.build()
        state = json.loads((self.root / "data/upstream-state.json").read_text(encoding="utf-8"))
        first = state["inputs"]["sources"][0]
        self.assertEqual(first["raw_sha256"], update.sha256((self.offline / "block.txt").read_bytes()))
        self.assertEqual(first["url"], self.catalog["sources"][0]["url"])
        self.assertNotIn("checked_at", state)
        self.assertEqual(len(state["inputs"]["generator_sha256"]), 64)

    @staticmethod
    def ordered_compile(*args):
        return {
            "rules/ads-domain.yaml": "payload:\n  - '+.ads.example'\n",
            "rules/domain-stage-02-allow.yaml": "payload:\n  - 'keep.ads.example'\n",
        }, {"ui": {
            "domain_mode": "ordered-stages",
            "required_domain_order": [
                {"path": "rules/domain-stage-02-allow.yaml", "policy": "DIRECT"},
                {"path": "rules/ads-domain.yaml", "policy": "REJECT"},
            ],
        }}

    def test_ordered_stages_fail_closed_without_changing_published_outputs(self):
        self.build()
        before = generated_snapshot(self.root, include_mtime=True)
        self.change_source()
        with self.assertRaisesRegex(update.UpdateError, "ordered-stages"):
            self.build(compiler=self.ordered_compile)
        self.assertEqual(generated_snapshot(self.root, include_mtime=True), before)

    def test_ordered_stages_publish_only_after_explicit_opt_in(self):
        self.build()
        write_json(self.root / "config/personal.json", {
            "disabled_sources": [], "allow_ordered_domain_stages": True,
        })
        result = self.build(compiler=self.ordered_compile)
        self.assertTrue(result["changed"])
        self.assertTrue((self.root / "rules/domain-stage-02-allow.yaml").is_file())
        report = json.loads((self.root / "data/report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["ui"]["domain_mode"], "ordered-stages")

    def test_bad_artifact_paths_do_not_escape_or_modify_outputs(self):
        self.build()
        before = generated_snapshot(self.root, include_mtime=True)
        self.change_source()
        for relative in ("../outside.txt", "rules/../../outside.txt", "/outside.txt",
                         "rules\\outside.txt", "data/report.json"):
            with self.subTest(path=relative), self.assertRaises(update.UpdateError):
                self.build(compiler=lambda *args: ({relative: "unsafe"}, {}))
            self.assertEqual(generated_snapshot(self.root, include_mtime=True), before)
        self.assertFalse((self.base / "outside.txt").exists())

    def test_invalid_source_id_cannot_escape_offline_folder(self):
        self.catalog["sources"][0]["id"] = "../outside"
        write_json(self.root / "config/upstreams.json", self.catalog)
        with self.assertRaises(update.UpdateError):
            self.build()
        self.assertEqual(generated_snapshot(self.root), {})

    def test_offline_symlink_cannot_read_outside_input_folder(self):
        target = self.base / "external.txt"
        target.write_text("HOST,external.example,REJECT\n", encoding="utf-8")
        source = self.offline / "block.txt"
        source.unlink()
        try:
            source.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"Symlinks are not available: {exc}")
        with self.assertRaises(update.UpdateError):
            self.build()
        self.assertEqual(generated_snapshot(self.root), {})

    def test_output_symlink_cannot_write_outside_repository(self):
        outside = self.base / "external-output"
        outside.mkdir()
        try:
            (self.root / "rules").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symlinks are not available: {exc}")
        with self.assertRaises(update.UpdateError):
            self.build()
        self.assertEqual(list(outside.iterdir()), [])

    def test_filesystem_error_rolls_back_and_leaves_state_unchanged(self):
        self.build()
        before = generated_snapshot(self.root)
        self.change_source()
        replace = os.replace
        calls = 0
        def fail_second_replace(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated filesystem failure")
            return replace(source, destination)
        with mock.patch.object(update.os, "replace", side_effect=fail_second_replace):
            with self.assertRaises(update.UpdateError):
                self.build()
        self.assertGreaterEqual(calls, 3)
        self.assertEqual(generated_snapshot(self.root), before)

    def test_obsolete_generated_file_is_removed_after_success(self):
        def initial(*args):
            return {"rules/a.txt": "ads.example\n", "rules/old-ip.txt": "203.0.113.0/24\n"}, {}
        self.build(compiler=initial)
        self.change_source()
        def replacement(*args):
            return {"rules/a.txt": "ads.example\n"}, {}
        self.build(compiler=replacement)
        self.assertFalse((self.root / "rules/old-ip.txt").exists())
        self.assertTrue((self.root / "rules/a.txt").is_file())

    def test_cli_failure_returns_nonzero_without_publishing(self):
        shutil.copyfile(Path(update.__file__), self.root / "scripts/update.py")
        process = subprocess.run(
            [sys.executable, "-X", "utf8", str(self.root / "scripts/update.py"),
             "--offline-dir", str(self.base / "missing")],
            text=True, encoding="utf-8", capture_output=True, timeout=15)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Update failed:", process.stderr)
        self.assertEqual(generated_snapshot(self.root), {})


if __name__ == "__main__":
    unittest.main()
