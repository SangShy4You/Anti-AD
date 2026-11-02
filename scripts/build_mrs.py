"""Derive and verify native Mihomo MRS files without changing rule coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable

if __package__:
    from . import update
else:
    import update


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "Meta v1.19.33"
SOURCES = (("domain", "rules/ads-domain.yaml", "rules/ads-domain.mrs"),
           ("ipcidr", "rules/ads-ip.yaml", "rules/ads-ip.mrs"))


class MrsBuildError(RuntimeError):
    """Native conversion or round-trip verification failed."""


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120, check=False)


def _command(runner, args: list[str]) -> str:
    try:
        result = runner(args)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MrsBuildError(f"Could not run native Mihomo: {exc}") from exc
    if result.returncode != 0:
        detail = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
        raise MrsBuildError(f"Mihomo exited with {result.returncode}: {detail[:1500]}")
    return (result.stdout or "") + "\n" + (result.stderr or "")


def _payload(raw: bytes, path: str) -> set[str]:
    """Read the deliberately small YAML subset emitted by our compiler."""
    try:
        lines = [line.strip() for line in raw.decode("utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        if lines == ["payload: []"]:
            return set()
        if not lines or lines[0] != "payload:":
            raise ValueError("missing payload header")
        values = []
        for line in lines[1:]:
            if not line.startswith("- "):
                raise ValueError("unexpected YAML structure")
            value = json.loads(line[2:])
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError("payload items must be nonempty strings")
            values.append(value)
        if len(values) != len(set(values)):
            raise ValueError("duplicate generated payload item")
        return set(values)
    except (ValueError, UnicodeDecodeError) as exc:
        raise MrsBuildError(f"Invalid generated YAML {path}: {exc}") from exc


def build_mrs(mihomo: Path, root: Path = ROOT, *,
              runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None) -> dict:
    root = Path(root).resolve(strict=True)
    mihomo = Path(mihomo).resolve(strict=True)
    if not root.is_dir() or not mihomo.is_file():
        raise MrsBuildError("Repository root must be a directory and Mihomo must be a file")
    runner = runner or _run
    version_output = _command(runner, [str(mihomo), "-v"])
    version_match = re.search(r"\bMihomo (Meta v\d+\.\d+\.\d+)\b", version_output)
    if version_match is None or version_match.group(1) != EXPECTED_VERSION:
        raise MrsBuildError(f"Expected Mihomo {EXPECTED_VERSION}; refusing an unreviewed converter")

    inputs = {relative: update._path(root, relative).read_bytes()
              for _, relative, _ in SOURCES}
    expected = {relative: _payload(raw, relative) for relative, raw in inputs.items()}
    # Validate output paths before invoking the tool, including existing symlinks.
    for relative in [*(output for _, _, output in SOURCES), "data/mrs-state.json"]:
        update._path(root, relative, output=True)
    payloads = {}
    with tempfile.TemporaryDirectory(prefix=".rule-update-mrs-", dir=root) as folder:
        stage = Path(folder)
        for behavior, relative, output in SOURCES:
            source_file = stage / f"{behavior}.yaml"
            mrs_file = stage / f"{behavior}.mrs"
            roundtrip_file = stage / f"{behavior}.txt"
            source_file.write_bytes(inputs[relative])
            _command(runner, [str(mihomo), "convert-ruleset", behavior, "yaml",
                              str(source_file), str(mrs_file)])
            if not mrs_file.is_file() or not mrs_file.stat().st_size:
                raise MrsBuildError(f"Mihomo did not produce a nonempty {behavior} MRS file")
            _command(runner, [str(mihomo), "convert-ruleset", behavior, "mrs",
                              str(mrs_file), str(roundtrip_file)])
            if not roundtrip_file.is_file():
                raise MrsBuildError(f"Mihomo did not produce the {behavior} round-trip text file")
            actual = {line.strip() for line in roundtrip_file.read_text(encoding="utf-8").splitlines()
                      if line.strip() and not line.lstrip().startswith("#")}
            if actual != expected[relative]:
                missing = len(expected[relative] - actual)
                added = len(actual - expected[relative])
                raise MrsBuildError(f"{behavior} round-trip mismatch: {missing} missing, {added} added; "
                                    "previous MRS outputs were preserved")
            payloads[output] = mrs_file.read_bytes()

    if any(update._path(root, path).read_bytes() != raw for path, raw in inputs.items()):
        raise MrsBuildError("YAML inputs changed during conversion; previous MRS outputs were preserved")
    state = {
        "schema_version": 1,
        "mihomo_version": EXPECTED_VERSION,
        "inputs": {path: update.sha256(raw) for path, raw in sorted(inputs.items())},
        "outputs": {path: update.sha256(raw) for path, raw in sorted(payloads.items())},
        "counts": {behavior: len(expected[relative]) for behavior, relative, _ in SOURCES},
    }
    payloads["data/mrs-state.json"] = update._json_bytes(state)
    written = update._publish(root, payloads)
    return {"changed": bool(written), "written": written, "counts": state["counts"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mihomo", type=Path, required=True,
                        help=f"Path to the checksum-verified official Mihomo {EXPECTED_VERSION} executable")
    parser.add_argument("--root", type=Path, default=ROOT, help="Generated rule repository directory")
    args = parser.parse_args(argv)
    try:
        result = build_mrs(args.mihomo, args.root)
    except Exception as exc:
        print(f"MRS build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified MRS round trips: {result['counts']['domain']} domain patterns, "
          f"{result['counts']['ipcidr']} IP prefixes; "
          f"{len(result['written'])} changed files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
