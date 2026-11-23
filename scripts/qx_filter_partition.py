"""Split a mixed QX filter into reviewed contiguous policy runs.

The concatenation of active rule rows is unchanged. No domain, IP, wildcard,
User-Agent or policy-overlap heuristic is needed: the original order itself is
the contract. Pure ``reject`` runs may use force-policy=reject; every other run
retains its per-rule policy. A topology or policy change stops publication.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import re

if __package__:
    from .qx_filters import parse_filters
else:
    from qx_filters import parse_filters


OUTPUT_NAME = re.compile(r"[a-z][a-z0-9-]*\.list\Z")


def _specifications(specs):
    if not isinstance(specs, list) or not specs:
        raise ValueError("Filter partitions need a nonempty ordered specification")
    outputs = set()
    previous_kind = None
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError("Filter partition specification must be an object")
        output, name, kind = spec.get("output"), spec.get("name"), spec.get("kind")
        if not isinstance(output, str) or not OUTPUT_NAME.fullmatch(output) or output in outputs:
            raise ValueError("Unsafe or duplicate filter partition output")
        outputs.add(output)
        if not isinstance(name, str) or not name.strip() or name != name.strip() or any(c in name for c in ",\r\n"):
            raise ValueError("Invalid filter partition resource name")
        if kind not in {"reject", "preserve"} or kind == previous_kind:
            raise ValueError("Filter partition kinds must alternate reject and preserve")
        previous_kind = kind
        allowed = spec.get("allowed_policies")
        if not isinstance(allowed, list) or not allowed or any(
            not isinstance(policy, str) or not policy.strip() or policy != policy.strip()
            or any(c in policy for c in ",\r\n") for policy in allowed
        ) or len(set(allowed)) != len(allowed):
            raise ValueError("Filter partition allowed policies must be unique explicit names")
        if (kind == "reject" and allowed != ["reject"]) or (kind == "preserve" and "reject" in allowed):
            raise ValueError("Only a pure plain-reject partition can force REJECT")
        if set(spec) - {"output", "name", "kind", "allowed_policies"}:
            raise ValueError("Unknown filter partition specification field")


def partition_ordered_filters(body: str, specs: list[dict]):
    """Return UTF-8 product bodies, ordered import metadata, and an audit report.

    ``specs`` names every expected contiguous run. It is deliberately reviewed,
    not inferred silently during future updates: an added or removed run could
    otherwise create a resource missing from an already installed QX profile.
    """
    _specifications(specs)
    if not isinstance(body, str) or "\ufeff" in body:
        raise ValueError("Filter partition input must be native text without a byte-order mark")
    parsed, issues = parse_filters({"id": "ordered-partition-input", "source_format": "qx", "force_policy": None}, body)
    if not parsed:
        raise ValueError("Cannot partition a filter without active rules")
    by_line = {rule.line: rule for rule in parsed}
    runs = []
    pending = []
    raw_rows = []
    for number, line in enumerate(body.splitlines(keepends=True), 1):
        rule = by_line.get(number)
        if rule is None:
            pending.append(line)
            continue
        kind = "reject" if rule.policy == "reject" else "preserve"
        if not runs or runs[-1]["kind"] != kind:
            runs.append({"kind": kind, "lines": [], "policies": Counter(), "first_line": number, "last_line": number, "rows": []})
        current = runs[-1]
        current["lines"].extend(pending)
        pending.clear()
        current["lines"].append(line)
        current["policies"][rule.policy] += 1
        current["last_line"] = number
        current["rows"].append(line)
        raw_rows.append(line)
    runs[-1]["lines"].extend(pending)
    if "".join("".join(run["lines"]) for run in runs) != body:
        raise ValueError("Filter partition source reconstruction failed")
    if len(runs) != len(specs) or any(run["kind"] != spec["kind"] for run, spec in zip(runs, specs)):
        raise ValueError("Filter partition topology changed; review resource order before publication")

    outputs, imports, details = {}, [], []
    reconstructed_rows = []
    for number, (run, spec) in enumerate(zip(runs, specs), 1):
        if not set(run["policies"]).issubset(spec["allowed_policies"]):
            raise ValueError("Filter partition policy changed; review allowed actions before publication")
        force_policy = "reject" if run["kind"] == "reject" else None
        header = ("# Personal Quantumult X ordered filter partition\n"
                  + f"# Part {number}/{len(runs)}: {spec['output']}\n"
                  + ("# All active rules use plain reject; force-policy=reject is safe.\n" if force_policy
                     else "# Preserve every rule's own policy; do not force a uniform REJECT.\n"))
        text = header + "".join(run["lines"])
        # No formatting, sorting, deduplication or qualifier changes occur here.
        reconstructed_rows.extend(run["rows"])
        outputs[spec["output"]] = text
        imports.append({"output": spec["output"], "name": spec["name"], "force_policy": force_policy})
        details.append({"output": spec["output"], "name": spec["name"], "kind": run["kind"],
                        "force_policy": force_policy, "rule_count": len(run["rows"]),
                        "policy_counts": dict(sorted(run["policies"].items())),
                        "first_source_line": run["first_line"], "last_source_line": run["last_line"],
                        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    if reconstructed_rows != raw_rows:
        raise ValueError("Filter partition active rule order changed")
    report = {"schema_version": 1, "source_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
              "input_rules": len(parsed), "output_rules": sum(part["rule_count"] for part in details),
              "active_rule_rows_preserved_exactly": True, "source_body_reconstructed_exactly": True,
              "partition_count": len(details), "partitions": details,
              "contract": "Every contiguous plain-reject/preserved-policy run has a reviewed resource; topology or policy drift aborts publication.",
              "input_parser_issues": issues}
    return outputs, imports, report
