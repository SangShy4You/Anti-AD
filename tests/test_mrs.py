"""Check that native-converter failures cannot publish partial MRS snapshots."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts import build_mrs


class FakeMihomo:
    """Exercise the external CLI contract with controlled broken round trips."""

    def __init__(self, *, broken=None, platform="windows amd64", version="v1.19.33"):
        self.broken = broken
        self.platform = platform
        self.version = version
        self.source_values = {}

    def __call__(self, args):
        if args[1:] == ["-v"]:
            return subprocess.CompletedProcess(args, 0,
                stdout=f"Mihomo Meta {self.version} {self.platform} with go1.26.10 build date\n",
                stderr="")
        _, command, behavior, source_format, source, target = args
        assert command == "convert-ruleset"
        target = Path(target)
        if source_format == "yaml":
            values = [json.loads(line.strip()[2:]) for line in Path(source).read_text(
                encoding="utf-8").splitlines() if line.strip().startswith("- ")]
            self.source_values[behavior] = values
            if self.broken != f"{behavior}-missing-mrs":
                target.write_bytes(b"fake-native-binary\0" + json.dumps(values).encode())
        else:
            if self.broken == f"{behavior}-missing-roundtrip":
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            values = list(reversed(self.source_values[behavior]))
            if self.broken == f"{behavior}-dropped-item":
                values.pop()
            if self.broken == f"{behavior}-added-item":
                values.append("unexpected.example")
            target.write_text("\n".join(values) + "\n", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


class MrsBuildTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(build_mrs.__file__).resolve().parents[1]
        self.temp = tempfile.TemporaryDirectory(prefix=".test-update-mrs-", dir=workspace)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "rules").mkdir()
        (self.root / "data").mkdir()
        self.mihomo = self.root / "verified-mihomo"
        self.mihomo.write_bytes(b"test executable placeholder")
        (self.root / "rules/ads-domain.yaml").write_text(
            '# generated\npayload:\n  - "+.ads.example"\n  - ".root-only.example"\n'
            '  - "exact.example"\n', encoding="utf-8")
        (self.root / "rules/ads-ip.yaml").write_text(
            'payload:\n  - "203.0.113.0/24"\n  - "2001:db8::/32"\n', encoding="utf-8")
        for relative in ("rules/ads-domain.mrs", "rules/ads-ip.mrs", "data/mrs-state.json"):
            (self.root / relative).write_bytes(b"previous published snapshot")

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                for folder in ("rules", "data") for path in (self.root / folder).iterdir()}

    def build(self, runner):
        return build_mrs.build_mrs(self.mihomo, self.root, runner=runner)

    def test_success_checks_both_types_and_second_build_is_unchanged(self):
        self.assertEqual(self.build(FakeMihomo())["counts"], {"domain": 3, "ipcidr": 2})
        before = self.snapshot()
        state = json.loads((self.root / "data/mrs-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["mihomo_version"], "Meta v1.19.33")
        self.assertEqual(set(state["outputs"]), {"rules/ads-domain.mrs", "rules/ads-ip.mrs"})
        # OS, architecture and compile-date differences must not create new state.
        result = self.build(FakeMihomo(platform="linux arm64"))
        self.assertFalse(result["changed"])
        self.assertEqual(self.snapshot(), before)

    def test_missing_or_different_round_trip_preserves_every_previous_output(self):
        for broken in ("domain-missing-mrs", "ipcidr-missing-mrs",
                       "domain-missing-roundtrip", "ipcidr-missing-roundtrip",
                       "domain-dropped-item", "ipcidr-dropped-item", "domain-added-item"):
            with self.subTest(broken=broken):
                before = self.snapshot()
                with self.assertRaises(build_mrs.MrsBuildError):
                    self.build(FakeMihomo(broken=broken))
                self.assertEqual(self.snapshot(), before)

    def test_converter_failure_and_unreviewed_version_preserve_outputs(self):
        def failed_converter(args):
            if args[1:] == ["-v"]:
                return FakeMihomo()(args)
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="invalid MRS")
        for runner in (failed_converter, FakeMihomo(version="v1.19.34")):
            with self.subTest(runner=runner):
                before = self.snapshot()
                with self.assertRaises(build_mrs.MrsBuildError):
                    self.build(runner)
                self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
