"""Fetch public rule data and publish a validated, deterministic local snapshot."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 32 * 1024 * 1024
SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
VOLATILE_KEYS = {
    "checked_at", "generated_at", "updated_at", "timestamp", "last_check",
    "last_checked_at", "fetched_at", "build_time", "run_timestamp",
}


class UpdateError(RuntimeError):
    """An update could not be completed without publishing incomplete data."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_body(raw: bytes, content_type: str = "", *, limit: int = MAX_BYTES) -> str:
    if not isinstance(raw, bytes):
        raise UpdateError("A source did not return bytes")
    if len(raw) > limit:
        raise UpdateError(f"Source exceeds the {limit}-byte size limit")
    if not raw.strip():
        raise UpdateError("Source is empty")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type in {"text/html", "application/xhtml+xml"}:
        raise UpdateError("Source returned an HTML page instead of rule data")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UpdateError("Source is not valid UTF-8 text") from exc
    start = text.lstrip().lower()
    if start.startswith(("<!doctype html", "<html", "<head", "<body")):
        raise UpdateError("Source contains an HTML page instead of rule data")
    if start.strip() in {"404: not found", "404 not found", "not found"}:
        raise UpdateError("Source contains a not-found response")
    if "\x00" in text:
        raise UpdateError("Source contains NUL bytes")
    return text


def fetch_url(url: str, *, timeout: float = 30, attempts: int = 3,
              limit: int = MAX_BYTES) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise UpdateError("Only HTTP(S) source URLs are supported")
    if attempts < 1:
        raise UpdateError("Download attempts must be positive")
    request = urllib.request.Request(url, headers={
        "User-Agent": "personal-rules-updater/1",
        "Accept": "text/plain, application/octet-stream, */*;q=0.5",
        "Accept-Encoding": "identity",
    })
    last_error = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if not 200 <= response.status < 300:
                    raise UpdateError(f"Unexpected HTTP status {response.status}")
                declared = response.headers.get("Content-Length")
                length = None
                if declared is not None:
                    try:
                        length = int(declared)
                    except ValueError:
                        pass
                    if length is not None and length > limit:
                        raise UpdateError(f"Source exceeds the {limit}-byte size limit")
                raw = response.read(limit + 1)
                if length is not None and len(raw) < length:
                    raise UpdateError("Source download is incomplete")
                validate_body(raw, response.headers.get("Content-Type", ""), limit=limit)
                return raw
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {408, 429} and exc.code < 500:
                raise UpdateError(f"Source returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(2 ** attempt, 4))
    raise UpdateError(f"Download failed after {attempts} attempts: {last_error}")


def _path(root: Path, relative: str, *, output: bool = False) -> Path:
    if not isinstance(relative, str) or not relative or any(c in relative for c in "\\:\x00\r\n"):
        raise UpdateError(f"Unsafe repository path: {relative!r}")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise UpdateError(f"Unsafe repository path: {relative!r}")
    if output and not (len(parts) >= 2 and parts[0] == "rules"
                       or relative in {"data/report.json", "data/upstream-state.json", "data/mrs-state.json", "data/advanced-state.json"}):
        raise UpdateError(f"Output path is outside the generated directories: {relative}")
    candidate = root.joinpath(*parts)
    try:
        candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise UpdateError(f"Repository path escapes its root: {relative}") from exc
    if output:
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise UpdateError(f"Generated output must not follow a symlink: {relative}")
        if candidate.exists() and not candidate.is_file():
            raise UpdateError(f"Generated output is not a regular file: {relative}")
    return candidate


def _load_config(root: Path, relative: str) -> tuple[dict, bytes]:
    raw = _path(root, relative).read_bytes()
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise UpdateError(f"Invalid JSON configuration: {relative}") from exc
    if not isinstance(document, dict):
        raise UpdateError(f"Configuration must be an object: {relative}")
    return document, raw


def _sources(catalog: dict, personal: dict) -> list[dict]:
    entries = catalog.get("sources")
    disabled = personal.get("disabled_sources", [])
    if not isinstance(entries, list) or not entries:
        raise UpdateError("The catalog must contain a nonempty sources list")
    if not isinstance(disabled, list) or any(not isinstance(x, str) for x in disabled):
        raise UpdateError("disabled_sources must be a list of source IDs")
    ids = set()
    active = []
    for source in entries:
        if not isinstance(source, dict):
            raise UpdateError("Source metadata must be an object")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id) or source_id in ids:
            raise UpdateError(f"Invalid or duplicate source ID: {source_id!r}")
        ids.add(source_id)
        if not isinstance(source.get("url"), str) or not source["url"]:
            raise UpdateError(f"Missing URL for {source_id}")
        if type(source.get("enabled", True)) is not bool:
            raise UpdateError(f"enabled must be boolean for {source_id}")
        if source.get("enabled", True) and source_id not in disabled:
            active.append(source)
    if set(disabled) - ids:
        raise UpdateError("disabled_sources contains an unknown source ID")
    return active


def _read_offline(folder: Path, source_id: str) -> bytes:
    candidate = folder / f"{source_id}.txt"
    try:
        candidate.resolve().relative_to(folder)
    except ValueError as exc:
        raise UpdateError(f"Offline source escapes the input folder: {source_id}") from exc
    with candidate.open("rb") as stream:
        return stream.read(MAX_BYTES + 1)


def _generator_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "scripts").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        safe = _path(root, relative)
        raw = safe.read_bytes()
        digest.update(relative.encode("utf-8") + b"\x00" + str(len(raw)).encode("ascii") + b"\x00" + raw)
    return digest.hexdigest()


def _without_timestamps(value):
    if isinstance(value, dict):
        return {k: _without_timestamps(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_without_timestamps(v) for v in value]
    return value


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _previous_state(root: Path) -> dict | None:
    path = _path(root, "data/upstream-state.json", output=True)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _outputs_match(root: Path, previous: dict) -> bool:
    outputs = previous.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        return False
    for relative, expected in outputs.items():
        if relative == "data/upstream-state.json":
            return False
        path = _path(root, relative, output=True)
        if not path.is_file() or sha256(path.read_bytes()) != expected:
            return False
    return True


def _publish(root: Path, payloads: dict[str, bytes | None]) -> list[str]:
    targets = {relative: _path(root, relative, output=True) for relative in payloads}
    changed = [relative for relative, path in targets.items()
               if (path.exists() if payloads[relative] is None
                   else not path.exists() or path.read_bytes() != payloads[relative])]
    if not changed:
        return []
    # The state marker is replaced only after every rule and report has succeeded.
    changed.sort(key=lambda relative: (relative in {"data/upstream-state.json", "data/mrs-state.json", "data/advanced-state.json"}, relative))
    with tempfile.TemporaryDirectory(prefix=".rule-update-", dir=root) as temp:
        stage = Path(temp)
        backups = {}
        for index, relative in enumerate(changed):
            staged = None
            if payloads[relative] is not None:
                staged = stage / f"new-{index}"
                staged.write_bytes(payloads[relative])
                if staged.read_bytes() != payloads[relative]:
                    raise UpdateError(f"Staged output verification failed: {relative}")
            target = targets[relative]
            backup = None
            if target.exists():
                backup = stage / f"old-{index}"
                shutil.copyfile(target, backup)
            backups[relative] = (staged, backup)
        for relative in changed:
            targets[relative].parent.mkdir(parents=True, exist_ok=True)
        replaced = []
        try:
            for relative in changed:
                _path(root, relative, output=True)
                if payloads[relative] is None:
                    targets[relative].unlink()
                else:
                    os.replace(backups[relative][0], targets[relative])
                replaced.append(relative)
        except Exception as exc:
            rollback_errors = []
            for relative in reversed(replaced):
                try:
                    backup = backups[relative][1]
                    if backup is None:
                        targets[relative].unlink()
                    else:
                        os.replace(backup, targets[relative])
                except OSError as rollback_error:
                    rollback_errors.append(f"{relative}: {rollback_error}")
            detail = f"; rollback errors: {rollback_errors}" if rollback_errors else ""
            raise UpdateError(f"Could not replace generated outputs: {exc}{detail}") from exc
    return changed


def _compile(catalog: dict, bodies: dict[str, str], personal: dict):
    if __package__:
        from .compiler import compile_profile
    else:
        from compiler import compile_profile
    return compile_profile(catalog, bodies, personal)


def update_repository(root: Path = ROOT, offline_dir: Path | None = None, *,
                      fetcher: Callable[[str], bytes] | None = None,
                      compiler: Callable | None = None) -> dict:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise UpdateError("Repository root must be a directory")
    catalog, catalog_raw = _load_config(root, "config/upstreams.json")
    personal, personal_raw = _load_config(root, "config/personal.json")
    sources = _sources(catalog, personal)
    if offline_dir is not None:
        offline_dir = Path(offline_dir).resolve(strict=True)
        if not offline_dir.is_dir():
            raise UpdateError("Offline input must be a directory")
    raw_bodies = {}
    errors = []
    def obtain(source):
        raw = (_read_offline(offline_dir, source["id"]) if offline_dir is not None
               else (fetcher or fetch_url)(source["url"]))
        return raw, validate_body(raw)
    bodies = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(obtain, source): source for source in sources}
        for future in as_completed(futures):
            source_id = futures[future]["id"]
            try:
                raw_bodies[source_id], bodies[source_id] = future.result()
            except Exception as exc:
                errors.append(f"{source_id}: {exc}")
    if errors:
        raise UpdateError("No outputs were changed; source fetch failed:\n" + "\n".join(sorted(errors)))
    inputs = {
        "catalog_sha256": sha256(catalog_raw),
        "personal_sha256": sha256(personal_raw),
        "generator_sha256": _generator_digest(root),
        "sources": [{"id": x["id"], "url": x["url"],
                     "raw_sha256": sha256(raw_bodies[x["id"]]),
                     "bytes": len(raw_bodies[x["id"]])} for x in sources],
    }
    previous = _previous_state(root)
    if (previous and previous.get("schema_version") == 1
            and previous.get("inputs") == inputs and _outputs_match(root, previous)):
        return {"changed": False, "compiled": False, "written": []}
    artifacts, report = (compiler or _compile)(catalog, bodies, personal)
    if not isinstance(artifacts, dict) or not artifacts or not isinstance(report, dict):
        raise UpdateError("Compiler must return nonempty artifacts and an audit object")
    ui = report.get("ui", {})
    if not isinstance(ui, dict):
        raise UpdateError("Compiler UI metadata must be an object")
    if (ui.get("domain_mode") == "ordered-stages"
            and personal.get("allow_ordered_domain_stages") is not True):
        raise UpdateError(
            "The new domain rules require ordered-stages in the client; no outputs were changed. "
            "Configure every stage in required_domain_order before explicitly setting "
            "personal.allow_ordered_domain_stages to true.")
    payloads = {}
    for relative, content in artifacts.items():
        _path(root, relative, output=True)
        if not relative.startswith("rules/") or not isinstance(content, str) or "\x00" in content:
            raise UpdateError(f"Invalid rule artifact: {relative!r}")
        payloads[relative] = content.encode("utf-8")
    payloads["data/report.json"] = _json_bytes(_without_timestamps(report))
    state = {"schema_version": 1, "inputs": inputs,
             "outputs": {path: sha256(raw) for path, raw in sorted(payloads.items())}}
    payloads["data/upstream-state.json"] = _json_bytes(state)
    # Remove only unchanged files recorded as our outputs by the preceding state.
    # For example, an IP list may disappear when its last rule is disabled.
    if previous and isinstance(previous.get("outputs"), dict):
        for relative, expected in previous["outputs"].items():
            if relative.startswith("rules/") and relative not in payloads:
                target = _path(root, relative, output=True)
                if target.exists() and sha256(target.read_bytes()) != expected:
                    raise UpdateError(f"Obsolete generated output was edited: {relative}")
                payloads[relative] = None
    written = _publish(root, payloads)
    return {"changed": bool(written), "compiled": True, "written": written}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-dir", type=Path,
                        help="Read <source-id>.txt snapshots instead of downloading")
    args = parser.parse_args(argv)
    try:
        result = update_repository(offline_dir=args.offline_dir)
    except Exception as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1
    if result["changed"]:
        print(f"Validated update: wrote {len(result['written'])} changed files.")
    else:
        print("No changes to rules or upstream state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
