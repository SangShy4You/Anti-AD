"""Reject warning-only native parses and provide the ASN lookup dependency."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request

if __package__:
    from . import update
else:
    import update

ROOT = Path(__file__).resolve().parents[1]
RELEASE_API = "https://api.github.com/repos/MetaCubeX/meta-rules-dat/releases/tags/latest"
ASN_URL = "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/GeoLite2-ASN.mmdb"


def providers_ready(providers: dict, expected: dict[str, int]) -> bool:
    # A declared provider can be JSON null while its asynchronous Init runs.
    return isinstance(providers, dict) and all(
        isinstance(providers.get(name), dict) and providers[name].get("ruleCount") == count
        for name, count in expected.items())


def prepare_asn(home: Path) -> None:
    metadata = json.loads(update.fetch_url(RELEASE_API, limit=2 * 1024 * 1024))
    matches = [item for item in metadata.get("assets", []) if item.get("name") == "GeoLite2-ASN.mmdb"]
    if len(matches) != 1:
        raise ValueError("Official release must contain exactly one ASN database")
    asset = matches[0]
    digest = asset.get("digest", "")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest) or asset.get("browser_download_url") != ASN_URL:
        raise ValueError("Official ASN asset metadata lacks a trusted URL or SHA256")
    expected = digest.split(":", 1)[1]
    target = home / "ASN.mmdb"
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
        return
    request = urllib.request.Request(ASN_URL, headers={"User-Agent": "Anti-AD-native-validation/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read(20 * 1024 * 1024 + 1)
    if (len(body) > 20 * 1024 * 1024 or len(body) != asset.get("size")
            or hashlib.sha256(body).hexdigest() != expected):
        raise ValueError("Official ASN database download failed size/SHA256 validation")
    with tempfile.NamedTemporaryFile(dir=home, delete=False, prefix=".asn-") as stage:
        stage.write(body)
        staging = Path(stage.name)
    try:
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)


def validate(mihomo: Path, config: Path, home: Path, *, download_asn=False) -> str:
    home.mkdir(parents=True, exist_ok=True)
    if download_asn:
        prepare_asn(home)
    environment = os.environ.copy()
    # Only this short-lived validation process may read the generated providers.
    environment["SAFE_PATHS"] = os.pathsep.join(filter(None, (str(ROOT), environment.get("SAFE_PATHS"))))
    mihomo = mihomo.resolve(strict=True)
    state = json.loads((ROOT / "data/advanced-state.json").read_text(encoding="utf-8"))
    expected = {}
    for source in state["mrs_sources"]:
        match = re.fullmatch(r"stage-(\d+)-(domain|ip|ip-no-resolve)\.mrs", Path(source["mrs_path"]).name)
        if match is None:
            raise ValueError("Unknown generated provider path")
        expected[f"personal_ads_s{match[1]}_{match[2].replace('-', '_')}"] = source["rule_count"]
    for path in (ROOT / "rules/advanced").glob("stage-*-extra.txt"):
        match = re.fullmatch(r"stage-(\d+)-extra\.txt", path.name)
        expected[f"personal_ads_s{match[1]}_extra"] = len([
            row for row in path.read_text(encoding="utf-8").splitlines()
            if row.strip() and not row.lstrip().startswith("#")])
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    secret = secrets.token_urlsafe(32)
    raw = config.resolve(strict=True).read_text(encoding="utf-8")
    # Validate newly generated files, never the previous published HTTP versions.
    raw = raw.replace('type: "http"', 'type: "file"')
    for line in raw.splitlines():
        if line.startswith('    path: "./rules/advanced/'):
            relative = json.loads(line.split(": ", 1)[1]).removeprefix("./")
            absolute = json.dumps(str((ROOT / relative).resolve()).replace("\\", "/"))
            raw = raw.replace(line, "    path: " + absolute)
    raw += (f'\nexternal-controller: "127.0.0.1:{port}"\nsecret: "{secret}"\n'
            'mixed-port: 0\nallow-lan: false\nlog-level: info\n')
    warnings = re.compile(r'\blevel="?(?:warning|error|fatal)\b')
    with tempfile.TemporaryDirectory(prefix=".native-", dir=home) as folder:
        temporary = Path(folder)
        config_path, log_path = temporary / "config.yaml", temporary / "core.log"
        config_path.write_text(raw, encoding="utf-8")
        command = [str(mihomo), "-d", str(home.resolve()), "-f", str(config_path.resolve())]
        checked = subprocess.run([*command, "-t"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=120, env=environment)
        output = checked.stdout + checked.stderr
        if checked.returncode or warnings.search(output):
            raise ValueError("Native parse failed or skipped rules:\n" + output)
        with log_path.open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=environment)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                loaded = False
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline and process.poll() is None:
                    request = urllib.request.Request(f"http://127.0.0.1:{port}/providers/rules",
                        headers={"Authorization": "Bearer " + secret})
                    try:
                        with opener.open(request, timeout=1) as response:
                            providers = json.load(response)["providers"]
                        if providers_ready(providers, expected):
                            loaded = True
                            break
                    except (OSError, ValueError, KeyError):
                        pass
                    time.sleep(0.1)
                runtime_log = log_path.read_text(encoding="utf-8", errors="replace")
                if not loaded or warnings.search(runtime_log):
                    raise ValueError("Native rule-provider initialization failed or skipped rules:\n" + runtime_log)
                output += f"Loaded and verified all {len(expected)} advanced providers without warnings.\n"
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mihomo", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "rules/advanced-merge.yaml")
    parser.add_argument("--home", type=Path, required=True, help="Separate native-validation cache directory")
    parser.add_argument("--download-asn", action="store_true")
    args = parser.parse_args()
    try:
        print(validate(args.mihomo, args.config, args.home, download_asn=args.download_asn), end="")
    except Exception as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
