"""Compile the personal ad profile. No networking and no third-party runtime.

UI exports are explicitly domain-only and IP-only projections. The ordered
classical fragment preserves expressible cross-type priority; neither export
implements QX HTTP rewrites or USER-AGENT matching.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import ipaddress
import json
import re


@dataclass(frozen=True, slots=True)
class Rule:
    kind: str
    value: str
    params: tuple[str, ...]
    source: str
    priority: int
    role: str
    policy: str

    def classical(self) -> str:
        kind, value = self.kind, self.value
        if kind == "DOMAIN-SUBDOMAIN":
            kind, value = "DOMAIN-WILDCARD", "*." + value
        return ",".join((kind, value, *self.params))


ALIASES = {
    "HOST": "DOMAIN", "DOMAIN": "DOMAIN",
    "HOST-SUFFIX": "DOMAIN-SUFFIX", "DOMAIN-SUFFIX": "DOMAIN-SUFFIX",
    "HOST-KEYWORD": "DOMAIN-KEYWORD", "DOMAIN-KEYWORD": "DOMAIN-KEYWORD",
    "HOST-WILDCARD": "DOMAIN-WILDCARD", "DOMAIN-WILDCARD": "DOMAIN-WILDCARD",
    "DOMAIN-REGEX": "DOMAIN-REGEX",
    "IP-CIDR": "IP-CIDR", "IP6-CIDR": "IP-CIDR6", "IP-CIDR6": "IP-CIDR6",
    "IP-ASN": "IP-ASN", "GEOIP": "GEOIP", "PROCESS-NAME": "PROCESS-NAME",
    "DST-PORT": "DST-PORT", "DEST-PORT": "DST-PORT",
}
DOMAIN_KINDS = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-SUBDOMAIN"}
IP_KINDS = {"IP-CIDR", "IP-CIDR6"}
OPTIONS = {"no-resolve", "force-remote-dns", "force-cellular", "multi-interface",
           "multi-interface-balance", "via-interface", "extended-matching"}


def _unique(values):
    return list(dict.fromkeys(values))


def _yaml_payload(values, title):
    title = str(title).replace("\n", " ").replace("\r", " ")
    if not values:
        return f"# {title}\npayload: []\n"
    return "# " + title + "\npayload:\n" + "".join(
        "  - " + json.dumps(v, ensure_ascii=False) + "\n" for v in values)


def _policy(source):
    policy = str(source.get("expected_policy", "REJECT" if source["role"] == "block" else "DIRECT"))
    if not policy or any(c in policy for c in ",\r\n"):
        raise ValueError(f"invalid policy for source {source.get('id')}")
    return policy.upper() if policy.lower() in {"direct", "reject"} else policy


def _domain(value):
    value = value.lower()
    if not value or value.endswith(".") or ".." in value:
        raise ValueError("empty domain, empty label, or trailing dot")
    if not re.fullmatch(r"[a-z0-9_\-\u0080-\uffff]+(?:\.[a-z0-9_\-\u0080-\uffff]+)*", value):
        raise ValueError("not a literal domain")
    return value


def _parse_source(source, body, priority, issues):
    if not isinstance(body, str) or not body.strip():
        raise ValueError(f"empty source {source['id']}")
    fmt = source.get("source_format", "mixed").lower().replace("-", "_")
    if fmt == "audited_qx_rewrite_domains":
        if __package__:
            from .rewrite_domains import extract_rule_source
        else:
            from rewrite_domains import extract_rule_source
        body = extract_rule_source(body)
        fmt = "domain_text"
    domainset = fmt in {"domainset", "surge_domainset"}
    native_domain = fmt in {"domain", "domain_text", "domain_yaml"}
    native_ip = fmt in {"ipcidr", "ipcidr_text", "ipcidr_yaml"}
    result = []
    recognized = 0
    yaml_header = False
    for lineno, raw in enumerate(body.splitlines(), 1):
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith(("#", "//", ";")):
            continue
        line = re.split(r"\s+(?:#|//)", line, maxsplit=1)[0].strip()
        location = f"{source['id']}:{lineno}"
        if (native_domain or native_ip) and line == "payload:":
            yaml_header = True
            continue
        if yaml_header:
            if not line.startswith("- "):
                raise ValueError(f"unsupported YAML structure at {location}")
            line = line[2:].strip()
            if line.startswith('"'):
                line = json.loads(line)
            elif line.startswith("'") and line.endswith("'"):
                line = line[1:-1].replace("''", "'")
            if not isinstance(line, str):
                raise ValueError(f"non-string domain/IP at {location}")
        if "," not in line:
            tokens = []
            if domainset:
                kind, value = ("DOMAIN-SUFFIX", line[1:]) if line.startswith(".") else ("DOMAIN", line)
            elif native_domain:
                if line.startswith("+."):
                    kind, value = "DOMAIN-SUFFIX", line[2:]
                elif line.startswith("."):
                    kind, value = "DOMAIN-SUBDOMAIN", line[1:]
                else:
                    kind, value = "DOMAIN", line
            elif native_ip:
                kind, value = ("IP-CIDR6" if ":" in line else "IP-CIDR"), line
            else:
                raise ValueError(f"unexpected non-rule structure at {location}: {line[:80]}")
        else:
            fields = [part.strip() for part in line.split(",")]
            raw_kind, value = fields[:2]
            raw_kind = raw_kind.upper().replace("_", "-")
            if raw_kind == "USER-AGENT":
                recognized += 1
                issues.append({"source": source["id"], "line": lineno, "rule": line,
                               "category": "unsupported-user-agent", "exported": False})
                continue
            if raw_kind not in ALIASES:
                raise ValueError(f"unknown rule type {raw_kind!r} at {location}")
            kind = ALIASES[raw_kind]
            tokens = fields[2:]
            if tokens and tokens[0].lower().split("=", 1)[0] not in OPTIONS:
                tokens = tokens[1:]  # original action is overridden by force-policy
        recognized += 1
        if not value:
            raise ValueError(f"empty rule payload at {location}")
        params = []
        for token in tokens:
            low = token.lower()
            if low == "no-resolve" and kind in IP_KINDS | {"GEOIP", "IP-ASN"}:
                params.append(low)
            elif token:
                issues.append({"source": source["id"], "line": lineno, "rule": line,
                               "category": "omitted-option", "option": token, "exported": True})
        if kind in DOMAIN_KINDS:
            # The historic NobyDa list contains one trailing-dot entry which the
            # previous migration already audited as invalid. Never silently fix it.
            if value.endswith(".") and value[:-1] and not value.endswith(".."):
                _domain(value[:-1])
                issues.append({"source": source["id"], "line": lineno, "rule": line,
                               "category": "invalid-trailing-dot-domain", "exported": False})
                continue
            try:
                value = _domain(value)
            except ValueError as exc:
                raise ValueError(f"invalid domain at {location}: {exc}") from exc
        elif kind in IP_KINDS:
            network = ipaddress.ip_network(value, strict=False)
            if network.version != (6 if kind == "IP-CIDR6" else 4):
                raise ValueError(f"IP family mismatch at {location}")
            value = str(network)
        elif kind in {"DOMAIN-KEYWORD", "DOMAIN-WILDCARD", "DOMAIN-REGEX"}:
            if any(c in value for c in "\r\n"):
                raise ValueError(f"invalid domain expression at {location}")
            if kind == "DOMAIN-KEYWORD":
                value = value.lower()
        elif kind == "GEOIP" and not re.fullmatch(r"[A-Za-z]{2}", value):
            issues.append({"source": source["id"], "line": lineno, "rule": line,
                           "category": "named-geoip-database", "exported": True})
        elif kind == "IP-ASN" and not value.isdigit():
            raise ValueError(f"invalid ASN at {location}")
        result.append(Rule(kind, value, tuple(_unique(params)), source["id"], priority,
                           source["role"], _policy(source)))
    if not recognized:
        raise ValueError(f"source has no rule rows: {source['id']}")
    return _unique(result)


class _Node:
    __slots__ = ("children", "exact", "suffix", "subdomain")

    def __init__(self):
        self.children = {}
        self.exact = self.suffix = self.subdomain = None


def _first(*rules):
    candidates = [r for r in rules if r is not None]
    return min(candidates, key=lambda r: r.priority) if candidates else None


def _blocked(rule):
    return rule is not None and rule.role == "block"


def _trie(records):
    root = _Node()
    for rule in records:
        if rule.kind not in DOMAIN_KINDS:
            continue
        node = root
        for label in reversed(rule.value.split(".")):
            node = node.children.setdefault(label, _Node())
        attr = {"DOMAIN": "exact", "DOMAIN-SUFFIX": "suffix", "DOMAIN-SUBDOMAIN": "subdomain"}[rule.kind]
        setattr(node, attr, _first(getattr(node, attr), rule))
    return root


def _positive_domain_projection(records):
    """Return a minimal positive domain set, or explicit negative-hole evidence.

    +.d covers root+descendants; .d covers descendants only. A hole below an
    already-blocked ancestor cannot in general be encoded by a finite positive
    domain set, so it must trigger ordered stages rather than broaden allow.
    """
    tree = _trie(records)
    result, holes, root_exceptions = [], [], []

    def visit(node, labels, inherited, covered):
        domain = ".".join(reversed(labels))
        root_rule = _first(inherited, node.suffix, node.exact)
        descendant_rule = _first(inherited, node.suffix, node.subdomain)
        root_block, desc_block = _blocked(root_rule), _blocked(descendant_rule)
        if covered:
            if not root_block or not desc_block:
                holes.append({"domain": domain, "root_blocked": root_block,
                              "descendants_blocked": desc_block,
                              "root_source": root_rule.source if root_rule else None,
                              "descendant_source": descendant_rule.source if descendant_rule else None})
        elif desc_block:
            result.append(("+." if root_block else ".") + domain)
            covered = True
            if not root_block:
                root_exceptions.append({"domain": domain, "allow_source": root_rule.source if root_rule else None,
                                        "allow_policy": root_rule.policy if root_rule else "FALLTHROUGH",
                                        "blocking_source": descendant_rule.source})
        elif root_block:
            result.append(domain)
        for label in sorted(node.children):
            visit(node.children[label], labels + (label,), descendant_rule, covered)

    for label in sorted(tree.children):
        visit(tree.children[label], (label,), None, False)
    return sorted(result), holes, root_exceptions


def _merge_intervals(intervals):
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1] + 1:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def _subtract(start, end, covered):
    result, cursor = [], start
    for lo, hi in covered:
        if hi < cursor:
            continue
        if lo > end:
            break
        if lo > cursor:
            result.append((cursor, min(end, lo - 1)))
        cursor = max(cursor, hi + 1)
        if cursor > end:
            break
    if cursor <= end:
        result.append((cursor, end))
    return result


def _ip_projection(records):
    result = []
    for version in (4, 6):
        covered, blocked = [], []
        for rule in records:
            if rule.kind not in IP_KINDS:
                continue
            network = ipaddress.ip_network(rule.value)
            if network.version != version:
                continue
            start, end = int(network.network_address), int(network.broadcast_address)
            if rule.role == "block":
                blocked.extend(_subtract(start, end, covered))
            covered = _merge_intervals([*covered, (start, end)])
        cls = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
        for start, end in _merge_intervals(blocked):
            result.extend(str(n) for n in ipaddress.summarize_address_range(cls(start), cls(end)))
    return result


def _stages(records):
    stages = []
    for rule in records:
        signature = (rule.priority, rule.role, rule.policy)
        # Adjacent sources with the same effective policy can be combined.
        if not stages or stages[-1]["role"] != rule.role or stages[-1]["policy"] != rule.policy:
            stages.append({"role": rule.role, "policy": rule.policy, "rules": []})
        stages[-1]["rules"].append(rule)
    return stages


def _manual_rules(personal):
    result = []
    for priority, role in ((-2, "allow"), (-1, "reject")):
        block = personal.get(role, {})
        if not isinstance(block, dict):
            raise ValueError(f"personal.{role} must be an object")
        source = {"id": "personal_" + role, "role": "block" if role == "reject" else "allow",
                  "expected_policy": "REJECT" if role == "reject" else personal.get("allow_policy", "DIRECT")}
        for key, kind in (("domains", "DOMAIN"), ("suffixes", "DOMAIN-SUFFIX"), ("ipcidrs", "IP-CIDR")):
            values = block.get(key, [])
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError(f"personal.{role}.{key} must be a string list")
            for value in values:
                if key == "ipcidrs":
                    net = ipaddress.ip_network(value, strict=False)
                    k, value = ("IP-CIDR6" if net.version == 6 else "IP-CIDR"), str(net)
                else:
                    k = kind
                    value = _domain(value.removeprefix("+.").lstrip(".") if key == "suffixes" else value)
                result.append(Rule(k, value, (), source["id"], priority, source["role"], _policy(source)))
    return _unique(result)


def _domain_matches(rule, host):
    if rule.kind == "DOMAIN":
        return host == rule.value
    if rule.kind == "DOMAIN-SUFFIX":
        return host == rule.value or host.endswith("." + rule.value)
    if rule.kind == "DOMAIN-SUBDOMAIN":
        return host.endswith("." + rule.value)
    if rule.kind == "DOMAIN-KEYWORD":
        return rule.value in host
    return False


def compile_profile(catalog: dict, bodies: dict[str, str], personal: dict):
    """Return deterministic rules/ artifacts and a JSON-serializable audit."""
    sources = catalog.get("sources")
    if not isinstance(sources, list):
        raise ValueError("catalog.sources must be a list")
    ids = [s.get("id") for s in sources]
    if any(not isinstance(sid, str) or not sid for sid in ids) or len(ids) != len(set(ids)):
        raise ValueError("source IDs must be nonempty and unique")
    disabled = personal.get("disabled_sources", [])
    if not isinstance(disabled, list) or any(s not in ids for s in disabled):
        raise ValueError("disabled_sources contains an unknown source")
    issues, records, source_reports = [], _manual_rules(personal), []
    ordered = sorted(enumerate(sources), key=lambda pair: (pair[1].get("original_order", pair[0]), pair[0]))
    for priority, (_, source) in enumerate(ordered):
        role = source.get("role")
        if role not in {"block", "allow", "routing", "ignore", "rewrite", "reference"}:
            raise ValueError(f"unknown source role {role!r} for {source['id']}")
        if role not in {"block", "allow"} or source["id"] in disabled or source.get("enabled") is False:
            source_reports.append({"id": source["id"], "status": "disabled-or-out-of-scope"})
            continue
        if source["id"] not in bodies:
            raise ValueError(f"missing body for active source {source['id']}")
        parsed = _parse_source(source, bodies[source["id"]], priority, issues)
        records.extend(parsed)
        source_report = {"id": source["id"], "status": "compiled", "role": role,
                         "policy": _policy(source), "rules": len(parsed),
                         "types": dict(Counter(r.kind for r in parsed))}
        if source.get("source_format") == "audited_qx_rewrite_domains":
            if __package__:
                from .rewrite_domains import audit_rule_source
            else:
                from rewrite_domains import audit_rule_source
            source_report["derivation"] = audit_rule_source(bodies[source["id"]])
        source_reports.append(source_report)
    if not any(r.role == "block" for r in records):
        raise ValueError("profile has no supported block rules")
    domains = [r for r in records if r.kind in DOMAIN_KINDS]
    domain_payload, holes, root_exceptions = _positive_domain_projection(domains)
    title = personal.get("name", "Personal ads")
    artifacts = {}
    domain_order = []
    if not holes:
        path = "rules/ads-domain.yaml"
        artifacts[path] = _yaml_payload(domain_payload, title + " / domain-only projection / REJECT")
        domain_order.append({"path": path, "behavior": "domain", "format": "yaml", "policy": "REJECT"})
        mode = "single-file"
    else:
        mode = "ordered-stages"
        # Positive-only files cannot encode a child allow hole under an ancestor
        # block. Preserve source precedence explicitly rather than broaden allow.
        main_written = False
        for index, stage in enumerate(_stages(domains), 1):
            stage_payload, stage_holes, _ = _positive_domain_projection(stage["rules"])
            # An all-allow stage is a positive set of matches, not a blocked set.
            if stage["role"] == "allow":
                positive = [Rule(r.kind, r.value, r.params, r.source, r.priority, "block", "REJECT") for r in stage["rules"]]
                stage_payload, stage_holes, _ = _positive_domain_projection(positive)
            assert not stage_holes
            if stage["role"] == "block" and not main_written:
                path = "rules/ads-domain.yaml"
                main_written = True
            else:
                path = f"rules/domain-stage-{index:02d}-{stage['role']}.yaml"
            artifacts[path] = _yaml_payload(stage_payload, title + " / ordered domain stage")
            domain_order.append({"path": path, "behavior": "domain", "format": "yaml", "policy": stage["policy"]})
    ip_payload = _ip_projection(records)
    artifacts["rules/ads-ip.yaml"] = _yaml_payload(ip_payload, title + " / IP-only projection / REJECT")
    # Ordered cross-type export. Domains, keywords and IP rules remain together
    # within each original policy stage; a provider does not silently carry actions.
    lines = ["# Merge fragment, not a complete VPN configuration.",
             "# Map every named policy before merging; QX rewrites/UA are not implemented.", "rule-providers:"]
    routes = []
    advanced_stages = _stages(records)
    for index, stage in enumerate(advanced_stages, 1):
        name = f"personal_stage_{index:02d}"
        lines.extend([f"  {name}:", "    type: inline", "    behavior: classical", "    payload:"])
        for rule in _unique(r.classical() for r in stage["rules"]):
            lines.append("      - " + json.dumps(rule, ensure_ascii=False))
        routes.append(f"RULE-SET,{name},{stage['policy']}")
    lines.append("rules:")
    lines.extend("  - " + json.dumps(route, ensure_ascii=False) for route in routes)
    artifacts["rules/advanced-fragment.yaml"] = "\n".join(lines) + "\n"
    extras = [r for r in records if r.kind not in DOMAIN_KINDS | IP_KINDS]
    # Evidence that cross-type precedence can differ from the UI projections.
    cross_type_examples = []
    for exception in root_exceptions:
        host = exception["domain"]
        hit = next((r for r in records if _domain_matches(r, host)), None)
        if hit and hit.kind not in DOMAIN_KINDS:
            cross_type_examples.append({"host": host, "earliest_expression": hit.classical(),
                                        "source": hit.source, "policy": hit.policy,
                                        "domain_projection_allows_root": True})
    reject_patterns = []
    for r in domains:
        if r.role == "block":
            reject_patterns.append(("+." if r.kind == "DOMAIN-SUFFIX" else "." if r.kind == "DOMAIN-SUBDOMAIN" else "") + r.value)
    report = {
        "profile": title, "sources": source_reports,
        "counts": {"source_local_unique_rules": len(records),
                   "source_local_unique_reject_domain_rows": len(reject_patterns),
                   "distinct_reject_domain_patterns": len(set(reject_patterns)),
                   "ui_domain_patterns": len(domain_payload) if not holes else None,
                   "ui_ip_prefixes": len(ip_payload), "advanced_stages": len(advanced_stages),
                   "advanced_only_rule_rows": len(extras), "issues": len(issues)},
        "ui": {"domain_mode": mode, "required_domain_order": domain_order,
               "ip": {"path": "rules/ads-ip.yaml", "behavior": "ipcidr", "format": "yaml", "policy": "REJECT"},
               "root_only_allow_exceptions_encoded_as_leading_dot": root_exceptions,
               "unrepresentable_single_file_holes": holes[:100],
               "cross_type_examples": cross_type_examples,
               "equivalence": "domain-only and IP-only projections; not full QX equivalence"},
        "issues": issues, "advanced_policy_order": routes,
        "artifacts": sorted(artifacts),
        "limitations": [
            "UI domain/ipcidr exports cannot preserve keyword, UA, rewrite, or all domain-versus-IP precedence.",
            "The advanced fragment preserves supported cross-type source order but requires existing named policies and compatible GEOIP/ASN data.",
            "Manual allow overrides manual reject, followed by upstream order; manual allow policy defaults to DIRECT.",
            "Only public source contents are compiled; QX device cache, filter_local and resource_parser_url may differ.",
            "No iOS Apps Connect import or runtime behavior is certified by compilation.",
        ],
    }
    return artifacts, report
