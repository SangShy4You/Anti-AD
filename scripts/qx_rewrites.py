"""Conservatively combine reviewed native Quantumult X rewrite resources.

This module does no I/O and never evaluates an upstream script or URL regex.
Its checks establish resource structure, not successful execution in QX.
"""
from __future__ import annotations

from collections import Counter
import fnmatch
import re
from urllib.parse import urlsplit


_RULE = re.compile(r"^(.+?)\s+(url-and-header|url)\s+(\S+)(?:[ \t]+(.*))?$", re.I)
_ANNOTATION = re.compile(r"^\{#.*?#\}\s*")
_HOSTNAME = re.compile(r"^hostname\s*=\s*(.*)$", re.I)
_FILTER = re.compile(
    r"^(?:host(?:-suffix|-keyword|-wildcard)?|domain(?:-suffix|-keyword|-wildcard|-regex)?"
    r"|user-agent|ip-cidr|ip6-cidr|ip-cidr6|ip-asn|geoip|dest-port|dst-port"
    r"|src-ip|src-port|process-name|process-path|and|or|not|final|match)\s*,", re.I)
_ACTIONS = {
    "reject", "reject-200", "reject-img", "reject-dict", "reject-array",
    "302", "307", "request-header", "response-header", "request-body",
    "response-body", "jsonjq-request-body", "jsonjq-response-body",
    "script-request-header", "script-request-body", "script-response-header",
    "script-response-body", "script-echo-response", "script-analyze-echo-response",
    "echo-response",
}
_NO_ARGUMENT = {"reject", "reject-200", "reject-img", "reject-dict", "reject-array"}
_SECTIONS = {"rewrite_local", "mitm", "filter_local", "rule"}


def _selections(source, field):
    """Exact active line -> explanation; support a compact dict or records."""
    value = source.get(field, {})
    if isinstance(value, dict):
        result = dict(value)
    elif isinstance(value, list):
        result = {}
        for row in value:
            if not isinstance(row, dict):
                raise ValueError(f"{source['id']}: {field} requires rules with reasons")
            key = row.get("rule", row.get("text"))
            if key in result:
                raise ValueError(f"{source['id']}: duplicate {field} selection")
            result[key] = row.get("reason")
    else:
        raise ValueError(f"{source['id']}: invalid {field}")
    for key, reason in result.items():
        if not isinstance(key, str) or not key.strip() or key != key.strip():
            raise ValueError(f"{source['id']}: invalid exact line in {field}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{source['id']}: {field} requires a reason")
    return result


def _stage(action):
    if action in {"request-header", "request-body", "jsonjq-request-body"} or action.startswith("script-request-"):
        return "request"
    if action in {"response-header", "response-body", "jsonjq-response-body"} or action.startswith("script-response-"):
        return "response"
    return "terminal"


def _origin(source, line, text):
    return {"source": source["id"], "url": source.get("url", ""), "line": line, "text": text}


def compile_rewrites(sources: list, bodies: dict) -> tuple[str, dict]:
    """Return a flat native QX remote resource and line-evidenced audit.

    The official remote-resource format has rewrite rows and an optional
    ``hostname`` line, without main-profile section headers. When copying this
    output into a main profile manually, put rewrite rows in ``[rewrite_local]``
    and the hostname line in the existing ``[mitm]`` section.

    ``sources`` order is authoritative. Optional source fields:
    - include_rules: exact active lines to allow (missing selections fail).
    - exclude_rules: exact line/reason mapping, or [{rule, reason}].
    - excluded_lines: the same mapping for explicitly unsupported content.
    - include_hostnames: exact upstream hostname entries to retain.

    Exact duplicate rules are removed. Conflicts in the same request/response/
    terminal stage use the first source occurrence. Different stages survive;
    their common matcher is reported so a reviewer can assess interaction.
    This priority is an integration choice, not a claim about all QX runtime
    matching modes. No regex equivalence or domain-wide widening is attempted.
    """
    if not isinstance(sources, list) or not sources:
        raise ValueError("rewrite sources must be a non-empty list")
    seen_ids = set()
    rules = []
    by_rule = {}
    by_matcher_stage = {}
    by_matcher = {}
    hostnames = []
    host_origins = {}
    report = {
        "schema_version": 1,
        "validation": "Static native QX structure only; no JavaScript executed and no on-device QX test.",
        "conflict_policy": "first selected source occurrence within a matching stage; retain different stages",
        "sources": [], "rules": rules, "duplicates": [], "conflicts": [],
        "cross_stage_matches": [], "filter_lines": [], "exclusions": [],
        "hostname_origins": [], "hostname_conflicts": [], "script_urls": [],
        "script_references": [], "local_script_references": [], "local_data_references": [],
        "source_metadata": [],
    }
    for source in sources:
        sid = source.get("id")
        if not isinstance(sid, str) or not sid or sid in seen_ids:
            raise ValueError("rewrite source IDs must be unique non-empty strings")
        seen_ids.add(sid)
        body = bodies.get(sid)
        if not isinstance(body, str) or not body.strip():
            raise ValueError(f"{sid}: empty or missing rewrite source")
        if re.match(r"\s*(?:<!doctype\s+html|<html\b)", body.lstrip("\ufeff"), re.I):
            raise ValueError(f"{sid}: HTML is not a rewrite resource")
        excluded_rules = _selections(source, "exclude_rules")
        excluded_lines = _selections(source, "excluded_lines")
        include = source.get("include_rules")
        if include is not None:
            if not isinstance(include, list) or any(not isinstance(x, str) or not x.strip() or x != x.strip() for x in include):
                raise ValueError(f"{sid}: invalid include_rules")
            if len(set(include)) != len(include):
                raise ValueError(f"{sid}: duplicate include_rules")
            include = set(include)
        requested = {"include_rules": include or set(), "exclude_rules": set(excluded_rules), "excluded_lines": set(excluded_lines)}
        observed = {key: set() for key in requested}
        selected_hostnames = source.get("include_hostnames")
        if selected_hostnames is not None:
            if not isinstance(selected_hostnames, list) or any(not isinstance(x, str) or not x.strip() for x in selected_hostnames):
                raise ValueError(f"{sid}: invalid include_hostnames")
            selected_hostnames = {x.strip().lower() for x in selected_hostnames}
        source_hosts = []
        observed_hosts = set()
        counts = Counter()
        section = ""
        for number, raw in enumerate(body.lstrip("\ufeff").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith(("#", ";", "//")):
                continue
            evidence = _origin(source, number, line)
            for field, selections in requested.items():
                if line in selections:
                    observed[field].add(line)
            if line in excluded_lines:
                report["exclusions"].append({**evidence, "kind": "explicit-line", "reason": excluded_lines[line]})
                counts["explicit_lines_excluded"] += 1
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().lower()
                if section not in _SECTIONS:
                    raise ValueError(f"{sid}:{number}: unsupported section {line}")
                continue
            match = _HOSTNAME.fullmatch(line)
            if match:
                if section not in {"", "mitm"}:
                    raise ValueError(f"{sid}:{number}: hostname in unexpected section")
                for entry in match.group(1).split(","):
                    host = entry.strip().lower()
                    if not host:
                        continue
                    if host == "%append%":
                        report["source_metadata"].append({**evidence, "value": entry.strip(), "reason": "Surge append marker is not a hostname"})
                        continue
                    if re.search(r"[\s/\\=]", host):
                        raise ValueError(f"{sid}:{number}: invalid hostname entry {host!r}")
                    observed_hosts.add(host)
                    if selected_hostnames is not None and host not in selected_hostnames:
                        counts["hostnames_not_selected"] += 1
                        continue
                    source_hosts.append((host, evidence))
                continue
            line = _ANNOTATION.sub("", line, count=1)
            if _FILTER.match(line):
                report["filter_lines"].append({**evidence, "rule": line, "exported": False, "reason": "route rule collected for caller; not a rewrite"})
                counts["filter_lines_collected"] += 1
                continue
            match = _RULE.fullmatch(line)
            if not match:
                raise ValueError(f"{sid}:{number}: unsupported active rewrite content {line[:120]!r}")
            matcher, marker, action, argument = match.groups()
            marker, action = marker.lower(), action.lower()
            argument = argument or ""
            if not matcher.strip() or action not in _ACTIONS:
                raise ValueError(f"{sid}:{number}: unsupported rewrite action {action!r}")
            if marker == "url-and-header" and len(matcher.split(None, 1)) != 2:
                raise ValueError(f"{sid}:{number}: url-and-header requires URL and header matchers")
            if (action in _NO_ARGUMENT and argument) or (action not in _NO_ARGUMENT and not argument):
                raise ValueError(f"{sid}:{number}: invalid argument for {action}")
            counts["input_rules"] += 1
            if evidence["text"] in excluded_rules:
                report["exclusions"].append({**evidence, "kind": "explicit-rule", "reason": excluded_rules[evidence["text"]]})
                counts["rules_excluded"] += 1
                continue
            if include is not None and evidence["text"] not in include:
                report["exclusions"].append({**evidence, "kind": "not-allowlisted", "reason": "not selected by exact include_rules"})
                counts["rules_not_selected"] += 1
                continue
            counts["selected_rules"] += 1
            canonical = f"{matcher} {marker} {action}" + (f" {argument}" if argument else "")
            stage = _stage(action)
            key = (matcher, marker, stage)
            if canonical in by_rule:
                winner = by_rule[canonical]
                winner["origins"].append(evidence)
                report["duplicates"].append({"rule": canonical, "kept": winner["origins"][0], "removed": evidence})
                counts["duplicates_removed"] += 1
                continue
            entry = {"rule": canonical, "matcher": matcher, "marker": marker, "action": action,
                     "argument": argument, "stage": stage, "origins": [evidence]}
            if key in by_matcher_stage:
                winner = by_matcher_stage[key]
                report["conflicts"].append({"matcher": matcher, "marker": marker, "stage": stage,
                                            "resolution": "first-source-wins", "kept": winner,
                                            "excluded": entry})
                counts["conflicts_excluded"] += 1
                continue
            common_key = (matcher, marker)
            for previous in by_matcher.get(common_key, []):
                report["cross_stage_matches"].append({"matcher": matcher, "marker": marker,
                                                       "kept_stages": [previous["stage"], stage],
                                                       "rules": [previous["rule"], canonical],
                                                       "reason": "different processing stages retained; interaction requires QX testing"})
            by_matcher.setdefault(common_key, []).append(entry)
            by_matcher_stage[key] = entry
            by_rule[canonical] = entry
            rules.append(entry)
            counts["exported_rules"] += 1
        for field, wanted in requested.items():
            if wanted - observed[field]:
                raise ValueError(f"{sid}: stale {field}; exact selected line is missing")
        if selected_hostnames is not None and selected_hostnames - observed_hosts:
            raise ValueError(f"{sid}: stale include_hostnames; selected hostname is missing")
        if counts["input_rules"] == 0:
            raise ValueError(f"{sid}: no native rewrite rules found")
        # A later source can supply the MitM host required by an exact duplicate.
        if counts["selected_rules"]:
            for host, evidence in source_hosts:
                if host not in host_origins:
                    hostnames.append(host)
                    host_origins[host] = []
                host_origins[host].append(evidence)
        report["sources"].append({"id": sid, "name": source.get("name", sid), **dict(sorted(counts.items()))})
    if not rules:
        raise ValueError("selection exports no rewrite rules")
    for host in hostnames:
        report["hostname_origins"].append({"hostname": host, "origins": [
            {key: value for key, value in origin.items() if key != "text"}
            for origin in host_origins[host]]})
    negative = [host for host in hostnames if host.startswith("-")]
    positive = [host for host in hostnames if not host.startswith("-")]
    for excluded in negative:
        for included in positive:
            if included == excluded[1:] or (not any(c in included for c in "*?") and fnmatch.fnmatchcase(included, excluded[1:])):
                report["hostname_conflicts"].append({"exclusion": excluded, "inclusion": included, "resolution": "both retained for explicit review"})
    for entry in rules:
        if entry["action"].startswith("script-"):
            ref = entry["argument"]
            evidence = {"reference": ref, "rule": entry["rule"], "origins": entry["origins"]}
            parts = urlsplit(ref)
            if parts.scheme.lower() in {"http", "https"}:
                if not parts.netloc or parts.username or parts.password or any(c.isspace() for c in ref):
                    raise ValueError(f"invalid script URL in {entry['rule']!r}")
                if ref not in report["script_urls"]:
                    report["script_urls"].append(ref)
                report["script_references"].append(evidence)
            else:
                report["local_script_references"].append(evidence)
        elif entry["action"] == "echo-response":
            report["local_data_references"].append({"argument": entry["argument"], "rule": entry["rule"], "origins": entry["origins"]})
    report["actions"] = dict(sorted(Counter(entry["action"] for entry in rules).items()))
    report["counts"] = {"rules": len(rules), "hostnames": len(hostnames), "script_urls": len(report["script_urls"]),
                        "exact_duplicates_removed": len(report["duplicates"]), "conflicts_excluded": len(report["conflicts"]),
                        "filter_lines_collected": len(report["filter_lines"])}
    snippet = "# Personal QX rewrites; generated from reviewed sources.\n"
    snippet += "\n".join(entry["rule"] for entry in rules) + "\n"
    if hostnames:
        snippet += "\nhostname = " + ", ".join(hostnames) + "\n"
    return snippet, report
