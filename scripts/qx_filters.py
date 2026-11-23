"""Compile ordered, native Quantumult X filters without executing source code.

The compiler preserves source order, policies and supported QX qualifiers. It
only removes an identical later match with identical qualifiers. In particular,
it does not replace keyword/user-agent rules with domain-only approximations,
or collapse parent/child domain rules across intervening policies.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import ipaddress
import re
from typing import Mapping, Sequence


ALIASES = {
    "host": "host", "domain": "host",
    "host-suffix": "host-suffix", "domain-suffix": "host-suffix",
    "host-keyword": "host-keyword", "domain-keyword": "host-keyword",
    "host-wildcard": "host-wildcard", "domain-wildcard": "host-wildcard",
    "user-agent": "user-agent",
    "ip-cidr": "ip-cidr", "ip4-cidr": "ip-cidr",
    "ip6-cidr": "ip6-cidr", "ip-cidr6": "ip6-cidr",
    "geoip": "geoip", "ip-asn": "ip-asn",
}
FLAG_OPTIONS = {
    "no-resolve", "force-remote-dns", "force-cellular", "multi-interface",
    "multi-interface-balance", "extended-matching",
}
VALUE_OPTIONS = {"via-interface"}
BUILTIN_POLICIES = {
    "direct", "proxy", "reject", "reject-drop", "reject-no-drop",
    "reject-tinygif", "reject-dict", "reject-array", "reject-200",
    "reject-img",
}
DOMAIN_FORMATS = {"domainset", "surge_domainset", "domain", "domain_text"}


@dataclass(frozen=True, slots=True)
class FilterRule:
    kind: str
    value: str
    policy: str
    options: tuple[str, ...]
    source: str
    line: int

    @property
    def match_key(self):
        return (self.kind, self.value, self.options)

    def render(self) -> str:
        return ", ".join((self.kind, self.value, self.policy, *self.options))


def _policy(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing/invalid policy at {location}")
    value = value.strip()
    if any(c in value for c in ",\r\n") or value.startswith(("#", ";", "//")):
        raise ValueError(f"invalid policy at {location}")
    return value.lower() if value.lower() in BUILTIN_POLICIES else value


def _forced_policy(source: Mapping) -> str | None:
    # expected_policy is the original catalog's force-policy. Setting an explicit
    # null force_policy opts into retaining the action from each source row.
    value = source.get("force_policy", source.get("expected_policy"))
    return None if value is None else _policy(value, str(source.get("id", "source")))


def _option(token: str, location: str) -> str:
    name, separator, value = token.partition("=")
    name = name.strip().lower()
    if name in FLAG_OPTIONS and not separator:
        return name
    if name in VALUE_OPTIONS and separator and value.strip():
        return name + "=" + value.strip()
    raise ValueError(f"unknown or malformed QX filter option {token!r} at {location}")


def _is_option(token: str) -> bool:
    return token.lower().split("=", 1)[0] in FLAG_OPTIONS | VALUE_OPTIONS


def _value(kind: str, value: str, location: str, issues: list[dict]) -> str:
    if not value or any(c in value for c in "\r\n,"):
        raise ValueError(f"empty/malformed filter value at {location}")
    if kind in {"host", "host-suffix"}:
        if not re.fullmatch(r"[\w\-]+(?:\.[\w\-]+)*\.?", value, re.UNICODE):
            raise ValueError(f"invalid literal domain {value!r} at {location}")
        if value.endswith("."):
            # A historic NobyDa row has a final dot. Preserve that literal form;
            # removing it would silently make a previously distinct match live.
            issues.append({"location": location, "kind": "trailing-dot-preserved",
                           "value": value})
        return value.lower()
    if kind in {"host-keyword", "host-wildcard"}:
        if any(c.isspace() for c in value):
            raise ValueError(f"whitespace in domain pattern at {location}")
        return value.lower()
    if kind in {"ip-cidr", "ip6-cidr"}:
        network = ipaddress.ip_network(value, strict=False)
        if network.version != (4 if kind == "ip-cidr" else 6):
            raise ValueError(f"IP family mismatch at {location}")
        return str(network)
    if kind == "ip-asn":
        if not value.isascii() or not value.isdecimal():
            raise ValueError(f"invalid ASN at {location}")
        number = int(value)
        if not 0 < number <= 4294967295:
            raise ValueError(f"ASN out of range at {location}")
        return str(number)
    if kind == "geoip":
        if not re.fullmatch(r"[A-Za-z]{2}", value):
            raise ValueError(f"unsupported GEOIP country at {location}")
        return value.lower()
    # USER-AGENT values are case-sensitive patterns and may contain percent-
    # encoded text. Do not lowercase, URL-decode, or replace them with hosts.
    return value


def parse_filters(source: Mapping, body: str) -> tuple[list[FilterRule], list[dict]]:
    """Parse one source. Metadata accepts id/source_format/expected_policy.

    Native/mixed QX or Surge rows must contain known match kinds. Explicit
    Surge DOMAIN-SET input distinguishes .suffix from an exact bare domain.
    Unsupported formats/options fail closed rather than being dropped.
    """
    sid = str(source.get("id", ""))
    if not sid or any(c in sid for c in "\r\n"):
        raise ValueError("source id is required")
    if not isinstance(body, str) or not body.strip():
        raise ValueError(f"empty filter source {sid}")
    fmt = str(source.get("source_format", "mixed")).lower().replace("-", "_")
    if fmt not in {"mixed", "qx", "quantumultx", "surge", *DOMAIN_FORMATS}:
        raise ValueError(f"unsupported filter source format {fmt!r} for {sid}")
    forced = _forced_policy(source)
    exclusions = source.get("exclude_rules", {})
    if (not isinstance(exclusions, Mapping)
            or any(not isinstance(k, str) or not isinstance(v, str) or not v.strip()
                   for k, v in exclusions.items())):
        raise ValueError(f"exclude_rules must map original lines to non-empty reasons for {sid}")
    observed_exclusions = set()
    rules, issues = [], []
    for lineno, original in enumerate(body.splitlines(), 1):
        line = original.strip().lstrip("\ufeff")
        if not line or line.startswith(("#", ";", "//")):
            continue
        if line in exclusions:
            observed_exclusions.add(line)
            issues.append({"location": f"{sid}:{lineno}", "kind": "explicit-exclusion",
                           "rule": line, "reason": exclusions[line]})
            continue
        line = re.split(r"\s+(?:#|//)", line, maxsplit=1)[0].strip()
        location = f"{sid}:{lineno}"
        if "," not in line:
            if fmt not in DOMAIN_FORMATS or forced is None:
                raise ValueError(f"unexpected non-rule text at {location}: {line[:70]!r}")
            if line.startswith("+.") and fmt not in {"domainset", "surge_domainset"}:
                kind, value = "host-suffix", line[2:]
            elif line.startswith("."):
                kind, value = (("host-suffix", line[1:])
                               if fmt in {"domainset", "surge_domainset"}
                               else ("host-wildcard", "*" + line))
            else:
                kind, value = "host", line
            policy, options = forced, ()
        else:
            fields = [field.strip() for field in line.split(",")]
            if len(fields) < 2:
                raise ValueError(f"incomplete filter at {location}")
            original_kind, value = fields[:2]
            key = original_kind.lower().replace("_", "-")
            if key not in ALIASES:
                raise ValueError(f"unsupported filter type {original_kind!r} at {location}")
            kind = ALIASES[key]
            rest = fields[2:]
            row_policy = None
            if rest and not _is_option(rest[0]):
                row_policy = _policy(rest.pop(0), location)
            if forced is None and row_policy is None:
                raise ValueError(f"filter has no policy at {location}")
            policy = forced if forced is not None else row_policy
            # Preserve option order: do not assume two interface or resolver
            # options commute. Only remove an identical repeated option.
            options = tuple(dict.fromkeys(_option(token, location) for token in rest))
        value = _value(kind, value, location, issues)
        rules.append(FilterRule(kind, value, policy, options, sid, lineno))
    if not rules:
        raise ValueError(f"source has no filter rows: {sid}")
    for line in exclusions.keys() - observed_exclusions:
        # Removal upstream is harmless; changed spelling must be reviewed by the
        # maintainer. Do not force historical rows to remain in a live source.
        issues.append({"location": sid, "kind": "exclusion-not-present",
                       "rule": line, "reason": exclusions[line]})
    return rules, issues


def compile_filters(sources: Sequence[Mapping], bodies: Mapping[str, str],
                    overrides: Sequence[str] = ()) -> tuple[str, dict]:
    """Return a native QX filter file and an auditable deduplication report.

    An explicit ``overrides`` sequence is parsed first without force-policy;
    all supplied sources are otherwise processed in the caller's order. This
    mirrors filter_remote priority and never sorts rows alphabetically.
    """
    prepared = []
    if overrides:
        prepared.append(({"id": "personal_overrides", "name": "个人优先规则",
                          "source_format": "qx", "force_policy": None},
                         "\n".join(overrides)))
    ids = set()
    disabled = []
    for source in sources:
        sid = str(source.get("id", ""))
        if sid in ids or sid == "personal_overrides":
            raise ValueError(f"duplicate/reserved source id: {sid}")
        ids.add(sid)
        if source.get("enabled", True) is False:
            disabled.append(sid)
            continue
        if sid not in bodies:
            raise ValueError(f"missing filter body: {sid}")
        prepared.append((source, bodies[sid]))
    seen, kept, summaries, conflicts, duplicate_samples, issues = {}, [], [], [], [], []
    duplicates = 0
    conflict_count = 0
    counts = Counter()
    for source, body in prepared:
        parsed, parsed_issues = parse_filters(source, body)
        issues.extend(parsed_issues)
        summary = {"id": source["id"], "name": source.get("name", source["id"]),
                   "url": source.get("url"), "input_rules": len(parsed),
                   "kept_rules": 0, "duplicate_rules": 0,
                   "forced_policy": _forced_policy(source),
                   "excluded_rules": sum(x["kind"] == "explicit-exclusion" for x in parsed_issues),
                   "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}
        for rule in parsed:
            prior = seen.get(rule.match_key)
            if prior is not None:
                duplicates += 1
                summary["duplicate_rules"] += 1
                sample = {"kept_source": prior.source, "kept_line": prior.line,
                          "removed_source": rule.source, "removed_line": rule.line,
                          "kept_rule": prior.render(), "removed_rule": rule.render()}
                if prior.policy != rule.policy:
                    conflict_count += 1
                    if len(conflicts) < 100:
                        conflicts.append(sample)
                elif len(duplicate_samples) < 100:
                    duplicate_samples.append(sample)
                continue
            seen[rule.match_key] = rule
            kept.append(rule)
            summary["kept_rules"] += 1
            counts[rule.kind] += 1
        summaries.append(summary)
    if not kept:
        raise ValueError("no enabled QX filter rules")
    text = "# Personal Quantumult X ordered filters\n"
    text += "# Source order and explicit policies are preserved; exact matches deduplicated.\n"
    last_source = None
    for rule in kept:
        if rule.source != last_source:
            text += "\n# Source: " + rule.source + "\n"
            last_source = rule.source
        text += rule.render() + "\n"
    report = {
        "schema_version": 1, "input_rules": sum(x["input_rules"] for x in summaries),
        "output_rules": len(kept), "duplicate_rules_removed": duplicates,
        "conflict_rules_removed_first_match_wins": conflict_count,
        "conflicts": conflicts, "duplicate_samples": duplicate_samples,
        "duplicate_samples_limited_to": 100,
        "conflict_samples_limited_to": 100,
        "type_counts": dict(sorted(counts.items())), "sources": summaries,
        "disabled_sources": disabled, "issues": issues,
        "deduplication": "same kind, normalized value and identical qualifiers; first source wins",
        "domain_parent_child_compaction": False,
        "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    return text, report
