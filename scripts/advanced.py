"""Build an optional ordered ad guard for merging into a full Mihomo config.

Allow stages use PASS inside a sub-rule, so the airport's existing main routing
decides their exit. This intentionally differs from QX's forced allow policies.
The result contains no nodes and implements no HTTP rewriting or JavaScript.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

if __package__:
    from . import compiler, update
else:
    import compiler
    import update


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://raw.githubusercontent.com/SangShy4You/Anti-AD/main"
SOURCE = "rules/advanced-fragment.yaml"
MERGE = "rules/advanced-merge.yaml"
STATE = "data/advanced-state.json"
SUB_RULE = "personal_ads"
MAIN_RULE = f"SUB-RULE,(OR,((NETWORK,tcp),(NETWORK,udp))),{SUB_RULE}"


class AdvancedError(RuntimeError):
    """The controlled source cannot be converted without losing its meaning."""


def _parse_fragment(raw: bytes) -> list[dict]:
    """Parse only the compiler-owned inline provider subset, never arbitrary YAML."""
    providers = {}
    routes = []
    current = None
    mode = None
    try:
        for line in raw.decode("utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line == "rule-providers:":
                if mode is not None:
                    raise ValueError("duplicate providers header")
                mode = "providers"
                continue
            if line == "rules:":
                if mode != "providers":
                    raise ValueError("misplaced rules header")
                mode = "rules"
                continue
            if mode == "rules":
                if not line.startswith("  - "):
                    raise ValueError("unsupported main rule syntax")
                expression = json.loads(line.strip()[2:])
                fields = expression.split(",")
                if len(fields) != 3 or fields[0] != "RULE-SET" or not fields[2]:
                    raise ValueError("expected an ordered provider action")
                if any(c in expression for c in "\r\n\0"):
                    raise ValueError("control characters in rule")
                routes.append((fields[1], fields[2]))
                continue
            match = re.fullmatch(r"  (personal_stage_\d{2,}):", line)
            if mode == "providers" and match:
                current = match.group(1)
                if current in providers:
                    raise ValueError("duplicate provider")
                providers[current] = {"rows": [], "fields": set()}
                continue
            if mode == "providers" and current is not None:
                if line in {"    type: inline", "    behavior: classical", "    payload:"}:
                    if line in providers[current]["fields"]:
                        raise ValueError("duplicate provider field")
                    providers[current]["fields"].add(line)
                    continue
                if line.startswith("      - "):
                    row = json.loads(line.strip()[2:])
                    if not isinstance(row, str) or not row or any(c in row for c in "\r\n\0"):
                        raise ValueError("invalid classical row")
                    providers[current]["rows"].append(row)
                    continue
            raise ValueError("unsupported inline fragment structure")
        expected_fields = {"    type: inline", "    behavior: classical", "    payload:"}
        if not routes or list(providers) != [name for name, _ in routes]:
            raise ValueError("provider order and main routes differ")
        if any(p["fields"] != expected_fields or not p["rows"] for p in providers.values()):
            raise ValueError("incomplete inline provider")
        return [{"name": name, "policy": action, "rows": providers[name]["rows"]}
                for name, action in routes]
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError) as exc:
        raise AdvancedError(f"Invalid compiler-owned advanced fragment: {exc}") from exc


def _base_url(value: str) -> str:
    value = value.rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise AdvancedError("The public base URL must be HTTPS without credentials, query or fragment")
    return value


def _yaml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _compile(raw: bytes, base_url: str) -> tuple[dict[str, bytes], dict]:
    stages = _parse_fragment(raw)
    base_url = _base_url(base_url)
    payloads = {}
    providers = {}
    guard_rules = []
    manifest = []
    stage_reports = []
    extra_count = 0

    def add_mrs(stage_number, label, behavior, values, action, no_resolve=False):
        if not values:
            return None
        name = f"personal_ads_s{stage_number:02d}_{label.replace('-', '_')}"
        stem = f"rules/advanced/stage-{stage_number:02d}-{label}"
        yaml_path, mrs_path = stem + ".yaml", stem + ".mrs"
        payloads[yaml_path] = compiler._yaml_payload(values, f"Optional advanced ads / {name}").encode("utf-8")
        providers[name] = {"type": "http", "behavior": behavior, "format": "mrs",
                           "url": f"{base_url}/{mrs_path}", "path": f"./{mrs_path}",
                           "interval": 86400}
        route = f"RULE-SET,{name},{action}" + (",no-resolve" if no_resolve else "")
        guard_rules.append(route)
        manifest.append({"behavior": behavior, "yaml_path": yaml_path, "mrs_path": mrs_path,
                         "rule_count": len(values)})
        return name

    for number, stage in enumerate(stages, 1):
        action = "REJECT" if stage["policy"] == "REJECT" else "PASS"
        if stage["policy"] in {"REJECT-DROP", "PASS", "PASS-RULE", "COMPATIBLE"}:
            raise AdvancedError(f"Unreviewed original stage policy: {stage['policy']}")
        domain_records = []
        ip_groups = defaultdict(list)
        extras = []
        for expression in dict.fromkeys(stage["rows"]):
            fields = expression.split(",")
            kind = fields[0]
            if len(fields) < 2 or not fields[1] or kind not in set(compiler.ALIASES) | {"DOMAIN-SUBDOMAIN"}:
                raise AdvancedError(f"Unsupported classical expression: {expression}")
            kind = compiler.ALIASES.get(kind, kind)
            value, params = fields[1], tuple(fields[2:])
            if kind in {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-SUBDOMAIN"}:
                if params:
                    raise AdvancedError(f"Domain options cannot be silently discarded: {expression}")
                value = compiler._domain(value)
                domain_records.append(compiler.Rule(kind, value, (), stage["name"], 0, "block", "REJECT"))
            elif kind in compiler.IP_KINDS:
                if params not in {(), ("no-resolve",)}:
                    raise AdvancedError(f"Unsupported IP options: {expression}")
                network = ipaddress.ip_network(value, strict=False)
                normalized = "IP-CIDR" if network.version == 4 else "IP-CIDR6"
                ip_groups[params].append(compiler.Rule(normalized, str(network), params,
                    stage["name"], 0, "block", "REJECT"))
            else:
                # In particular, keyword/regex/wildcard/ASN expressions retain
                # their original type; never turn an API/path into a whole domain.
                extras.append(expression)
        domain_values, holes, _ = compiler._positive_domain_projection(domain_records)
        if holes:
            raise AdvancedError("A same-policy stage unexpectedly requires allow holes")
        names = []
        name = add_mrs(number, "domain", "domain", domain_values, action)
        if name:
            names.append(name)
        if extras:
            name = f"personal_ads_s{number:02d}_extra"
            extra_path = f"rules/advanced/stage-{number:02d}-extra.txt"
            payloads[extra_path] = (
                f"# Optional advanced ads / {name}\n" + "\n".join(extras) + "\n"
            ).encode("utf-8")
            providers[name] = {"type": "http", "behavior": "classical", "format": "text",
                               "url": f"{base_url}/{extra_path}", "path": f"./{extra_path}",
                               "interval": 86400}
            guard_rules.append(f"RULE-SET,{name},{action}")
            names.append(name)
            extra_count += len(extras)
        for params in sorted(ip_groups):
            no_resolve = "no-resolve" in params
            label = "ip-no-resolve" if no_resolve else "ip"
            name = add_mrs(number, label, "ipcidr", compiler._ip_projection(ip_groups[params]),
                           action, no_resolve)
            if name:
                names.append(name)
        stage_reports.append({"source_stage": stage["name"], "original_policy": stage["policy"],
                              "action": action, "providers_in_order": names,
                              "classical_rows": len(set(stage["rows"])), "extra_rows": len(extras)})
    guard_rules.append("MATCH,PASS")
    lines = ["# Optional merge fragment, not a complete VPN or node subscription.",
             "# Merge providers/sub-rules; prepend rules before broad airport routing.",
             "# Allow stages PASS back to the original main rules, not forced QX exits.",
             "# Requires native SUB-RULE/PASS support. No HTTP rewriting or scripts.",
             "rule-providers:"]
    for name, provider in providers.items():
        lines.append(f"  {name}:")
        for key, value in provider.items():
            if key == "payload":
                lines.append("    payload:")
                lines.extend("      - " + _yaml(row) for row in value)
            else:
                lines.append(f"    {key}: " + (str(value) if isinstance(value, int) else _yaml(value)))
    lines.extend(["sub-rules:", f"  {SUB_RULE}:"])
    lines.extend("    - " + _yaml(row) for row in guard_rules)
    lines.extend(["rules:", "  - " + _yaml(MAIN_RULE)])
    payloads[MERGE] = ("\n".join(lines) + "\n").encode("utf-8")
    metadata = {
        "schema_version": 1, "mode": "allow-pass-preserve-airport-routing",
        "mrs_sources": manifest, "stages": stage_reports,
        "counts": {"stages": len(stages), "mrs_sources": len(manifest), "extra_rows": extra_count},
        "main_rule": MAIN_RULE, "sub_rule_name": SUB_RULE,
        "limitations": [
            "Allow matches return to airport main routing; original QX forced global-acceleration/DIRECT exits are intentionally not reproduced.",
            "Within-stage type grouping preserves the matched action but can change when DNS lookup occurs; IP no-resolve options remain explicit.",
            "This optional fragment requires full config merging and cannot be imported via the domain/ipcidr rule-set dialog.",
            "Disable the aggregate domain/IP UI ad rules when activating this ordered guard so they cannot defeat stage-specific allows.",
            "No QX USER-AGENT, URL rewrite, MITM or JavaScript behavior is implemented.",
            "ASN/GeoIP extras require compatible lookup data; native Mihomo validation does not certify AppsConnect support or iOS memory use.",
        ],
    }
    return payloads, metadata


def _owned_output(relative: str) -> bool:
    return relative == MERGE or re.fullmatch(
        r"rules/advanced/stage-\d{2,}-(?:(?:domain|ip|ip-no-resolve)\.yaml|extra\.txt)", relative
    ) is not None


def build_advanced(root: Path = ROOT, base_url: str = BASE_URL) -> dict:
    root = Path(root).resolve(strict=True)
    source = update._path(root, SOURCE)
    raw = source.read_bytes()
    payloads, metadata = _compile(raw, base_url)
    state = dict(metadata)
    state["inputs"] = {SOURCE: update.sha256(raw)}
    state["generator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    state["outputs"] = {relative: update.sha256(body) for relative, body in sorted(payloads.items())}
    state_path = update._path(root, STATE, output=True)
    if state_path.exists():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise AdvancedError("Existing advanced state is invalid; refusing destructive cleanup") from exc
        outputs = previous.get("outputs", {}) if isinstance(previous, dict) else {}
        if not isinstance(outputs, dict):
            raise AdvancedError("Existing advanced output metadata is invalid")
        for relative, expected in outputs.items():
            if _owned_output(relative) and relative not in payloads:
                obsolete = update._path(root, relative, output=True)
                if obsolete.exists() and update.sha256(obsolete.read_bytes()) != expected:
                    raise AdvancedError(f"Obsolete generated stage was edited: {relative}")
                payloads[relative] = None
    if source.read_bytes() != raw:
        raise AdvancedError("The advanced fragment changed during compilation")
    payloads[STATE] = update._json_bytes(state)
    written = update._publish(root, payloads)
    return {"changed": bool(written), "written": written, "metadata": state}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base-url", default=BASE_URL, help="Public HTTPS prefix for generated MRS files")
    args = parser.parse_args(argv)
    try:
        result = build_advanced(args.root, args.base_url)
    except Exception as exc:
        print(f"Advanced build failed: {exc}", file=sys.stderr)
        return 1
    counts = result["metadata"]["counts"]
    print(f"Optional ordered guard: {counts['stages']} stages, {counts['mrs_sources']} MRS inputs, "
          f"{counts['extra_rows']} advanced rows; {len(result['written'])} changed files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
