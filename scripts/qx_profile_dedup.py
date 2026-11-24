"""Deduplicate exact native QX rewrites across an explicit active profile.

Call after resource compilation and before replacing original script URLs with
immutable/personal URLs. Only identical canonical rule strings are coalesced.
Different actions, stages, headers, query strings and fragments remain distinct.
No I/O, JavaScript execution, regex implication or hostname widening occurs.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit


_MARKER = re.compile(r"\surl(?:-and-header)?\s")
_EXAMPLE_LIMIT = 100


def _product_path(products, filename):
    matches = [path for path in products if isinstance(path, str) and PurePosixPath(path).name == filename]
    if len(matches) != 1:
        raise ValueError(f"Profile product must resolve to exactly one output: {filename}")
    return matches[0]


def _script_metadata(report, rules):
    old_remote = {item["rule"]: item for item in report.get("script_references", [])}
    old_local = {item["rule"]: item for item in report.get("local_script_references", [])}
    old_data = {item["rule"]: item for item in report.get("local_data_references", [])}
    urls, remote, local, data = [], [], [], []
    for entry in rules:
        rule, action, argument = entry["rule"], entry["action"], entry.get("argument", "")
        if action.startswith("script-"):
            if urlsplit(argument).scheme.lower() in {"http", "https"}:
                ref = deepcopy(old_remote.get(rule, {"reference": argument, "rule": rule,
                                                      "origins": entry.get("origins", [])}))
                if ref["reference"] != argument:
                    raise ValueError("Script report differs from its canonical rule")
                remote.append(ref)
                if argument not in urls:
                    urls.append(argument)
            else:
                local.append(deepcopy(old_local.get(rule, {"reference": argument, "rule": rule,
                                                          "origins": entry.get("origins", [])})))
        elif action == "echo-response":
            data.append(deepcopy(old_data.get(rule, {"argument": argument, "rule": rule,
                                                    "origins": entry.get("origins", [])})))
    report["script_urls"] = urls
    report["script_references"] = remote
    report["local_script_references"] = local
    report["local_data_references"] = data


def deduplicate_profile(products: dict[str, bytes], reports: dict[str, dict], order: list[str]) -> list[dict]:
    """Modify later products/reports, returning deterministic per-file summaries.

    ``order`` consists of report filenames, e.g. ``['ads.conf','miniapps.conf']``.
    Product dictionary keys can include their repository directory prefix.
    Both dictionaries remain unchanged if validation fails, including when a
    later product would become empty. Hostnames, comments, headers and explicit
    hostname additions are retained byte-for-byte. At most 100 removed-rule
    examples are recorded across the entire returned profile summary.

    Original source ``input_rules`` counts are retained. For a changed resource,
    source ``exported_rules`` is updated and its original value is recorded as
    ``exported_rules_before_profile_dedup``. Resource-local duplicate/conflict
    audits remain available; profile removals are recorded separately.
    """
    if not isinstance(products, dict) or not isinstance(reports, dict) or not isinstance(order, list):
        raise ValueError("Products, reports and an explicit profile order are required")
    if any(not isinstance(name, str) or not name or PurePosixPath(name).name != name for name in order):
        raise ValueError("Profile order must contain resource filenames")
    if len(order) != len(set(order)):
        raise ValueError("Profile order repeats a resource")
    if any(name not in reports for name in order):
        raise ValueError("Profile order refers to an unknown report")

    seen, staged_products, staged_reports, summaries = {}, {}, {}, []
    examples_remaining = _EXAMPLE_LIMIT
    for index, filename in enumerate(order):
        path = _product_path(products, filename)
        raw = products[path]
        if not isinstance(raw, bytes):
            raise ValueError("Profile products must contain UTF-8 bytes")
        text = raw.decode("utf-8")
        lines = text.splitlines(keepends=True)
        report = deepcopy(reports[filename])
        rules = report.get("rules")
        if not isinstance(rules, list) or not rules:
            raise ValueError(f"Profile resource has no reported rewrites: {filename}")
        canonical = [entry.get("rule") for entry in rules]
        if any(not isinstance(rule, str) or not rule or "\n" in rule or "\r" in rule for rule in canonical):
            raise ValueError("A canonical rewrite must be one nonempty line")
        if len(canonical) != len(set(canonical)):
            raise ValueError("A resource contains duplicate canonical report entries")
        flat = Counter()
        for line in lines:
            value = line.rstrip("\r\n")
            if value.lstrip().startswith(("#", ";", "//")):
                continue
            if _MARKER.search(value):
                flat[value] += 1
        if set(flat) != set(canonical) or any(count != 1 for count in flat.values()):
            raise ValueError(f"Canonical reports differ from pre-pin native product: {filename}")

        kept, removed, examples = [], set(), []
        removed_sources = Counter()
        dependencies_on_earlier_files = []
        for entry in rules:
            rule = entry["rule"]
            if rule not in seen:
                seen[rule] = {"filename": filename, "entry": entry}
                kept.append(entry)
                continue
            winner = seen[rule]
            removed.add(rule)
            origins = entry.get("origins", [])
            removed_sources[(origins[0].get("source", "unknown-source") if origins else "unknown-source")] += 1
            if winner["filename"] not in dependencies_on_earlier_files:
                dependencies_on_earlier_files.append(winner["filename"])
            if examples_remaining:
                examples.append({"rule": rule, "kept_product": winner["filename"],
                                 "kept_origins": winner["entry"].get("origins", []),
                                 "removed_product": filename, "removed_origins": origins})
                examples_remaining -= 1
        if not kept:
            raise ValueError(f"Profile deduplication would empty a remote resource: {filename}")
        rewritten = "".join(line for line in lines if line.rstrip("\r\n") not in removed).encode("utf-8")
        summary = {"file": filename, "order_index": index, "rules_before": len(rules), "rules_after": len(kept),
                   "duplicates_removed": len(removed), "removed_source_counts": dict(sorted(removed_sources.items())),
                   "requires_earlier_products": dependencies_on_earlier_files,
                   "examples": examples, "profile_example_limit": _EXAMPLE_LIMIT,
                   "policy": "exact canonical rule only; first active profile resource wins"}
        report["rules"] = kept
        _script_metadata(report, kept)
        report["actions"] = dict(sorted(Counter(entry["action"] for entry in kept).items()))
        report.setdefault("counts", {})["rules"] = len(kept)
        report["counts"]["script_urls"] = len(report["script_urls"])
        report["counts"]["profile_exact_duplicates_removed"] = len(removed)
        if "selected_rule_coverage" in report:
            coverage = report["selected_rule_coverage"]
            coverage.update(stage="active profile", exported=len(kept),
                            profile_exact_duplicates_accounted_for=len(removed))
            if coverage["selected"] != (coverage["exported"] + coverage["exact_duplicates_accounted_for"]
                                        + coverage["profile_exact_duplicates_accounted_for"]):
                raise ValueError("Selected profile rewrite coverage is incomplete")
        report["profile_deduplication"] = summary
        for source in report.get("sources", []):
            removed_count = removed_sources[source["id"]]
            if removed_count:
                original = source.get("exported_rules", 0)
                if original < removed_count:
                    raise ValueError("Source exported count is inconsistent with removed rules")
                source["exported_rules_before_profile_dedup"] = original
                source["exported_rules"] = original - removed_count
                source["profile_duplicates_removed"] = removed_count
        staged_products[path] = rewritten
        staged_reports[filename] = report
        summaries.append(summary)

    # Commit only after every participating product has passed validation.
    products.update(staged_products)
    for filename, report in staged_reports.items():
        reports[filename].clear()
        reports[filename].update(report)
    return summaries
