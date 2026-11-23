"""Validate literal KOP in/out selections without copying upstream rule bodies.

This guard is pure: it performs no networking, file access or JavaScript
execution. Non-selected rule changes are allowed; ambiguous/missing selected
rows stop publication so a previously safe mixed-resource split cannot drift.
"""
from __future__ import annotations

import hashlib
import re


NATIVE_RULE = re.compile(r"^(.+?)\s+(url-and-header|url)\s+(\S+)(?:[ \t]+(.*))?$", re.I)
ANNOTATION = re.compile(r"^\{#.*?#\}\s*")


def validate_mixed_reference(body: str, spec: dict) -> dict:
    """Validate the same case-insensitive literal substring choice as KOP.

    ``spec`` has ``mode`` (``in``/``out``), ``keys`` (unique literal strings),
    ``expected_selected`` (the expected number of distinct matching rows) and
    an optional public ``title``. Each key must match exactly one active native
    rewrite. Rule bodies are never included in the returned report or errors.
    """
    if not isinstance(body, str) or not body.strip():
        raise ValueError("Mixed reference source is empty")
    if re.match(r"\s*(?:<!doctype\s+html|<html\b)", body.lstrip("\ufeff"), re.I):
        raise ValueError("Mixed reference source is HTML")
    if not isinstance(spec, dict):
        raise ValueError("Mixed reference specification must be an object")
    mode = spec.get("mode")
    if mode not in {"in", "out"}:
        raise ValueError("Mixed reference mode must be in or out")
    keys = spec.get("keys")
    if not isinstance(keys, list) or not keys or any(
        not isinstance(key, str) or not key or key != key.strip()
        or any(ord(char) < 32 for char in key) for key in keys
    ):
        raise ValueError("Mixed reference keys must be nonempty literal strings")
    folded = [key.upper() for key in keys]
    if len(set(folded)) != len(folded):
        raise ValueError("Mixed reference keys must be unique ignoring case")
    expected = spec.get("expected_selected", len(keys))
    if type(expected) is not int or expected < 1:
        raise ValueError("Expected selected count must be a positive integer")
    title = spec.get("title", "mixed-reference")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Mixed reference title must be a nonempty string")

    rows = []
    for number, raw in enumerate(body.lstrip("\ufeff").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        line = ANNOTATION.sub("", line, count=1)
        if not NATIVE_RULE.fullmatch(line):
            continue
        rows.append((number, line))
    if not rows:
        raise ValueError("Mixed reference contains no active native QX rewrites")
    matches = {key: [] for key in keys}
    selected = []
    for number, line in rows:
        upper = line.upper()
        matched = False
        for key, normalized in zip(keys, folded):
            if normalized in upper:
                matches[key].append(number)
                matched = True
        if matched:
            selected.append((number, line))
    bad_counts = [len(numbers) for numbers in matches.values() if len(numbers) != 1]
    if bad_counts:
        raise ValueError("Mixed reference selection drift: each key must match exactly one active rule")
    if len(selected) != expected:
        raise ValueError("Mixed reference selection drift: distinct selected count differs from the reviewed count")
    selected_count = len(selected)
    retained_count = selected_count if mode == "in" else len(rows) - selected_count
    return {
        "schema_version": 1,
        "title": title,
        "mode": mode,
        "source_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "input_rule_count": len(rows),
        "expected_selected": expected,
        "selected_rule_count": selected_count,
        "retained_rule_count": retained_count,
        "filtered_rule_count": len(rows) - retained_count,
        "per_key_matches": [{"key": key, "count": len(matches[key]), "lines": matches[key]} for key in keys],
        "selected_rule_evidence": [{"line": number, "sha256": hashlib.sha256(line.encode("utf-8")).hexdigest()}
                                   for number, line in selected],
        "rule_bodies_exported": False,
        "unselected_rule_changes_allowed": True,
        "matching": "KOP-compatible case-insensitive literal substring matching over active native QX rewrite rows",
    }
