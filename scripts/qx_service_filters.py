"""Review and convert service filter selections without executing a parser.

The supported KOP in/out subset is deliberately literal: out examines original
rows, in examines normalized rows, matching the existing reviewed profile.
Sources are still compiled and deduplicated by qx_filters in their original
intra-service order. Unknown policy/type drift stops transactional publication.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
from urllib.parse import unquote, urlsplit

if __package__:
    from .qx_filters import parse_filters, FLAG_OPTIONS, VALUE_OPTIONS
else:
    from qx_filters import parse_filters, FLAG_OPTIONS, VALUE_OPTIONS


def _parameters(url):
    result = {}
    for token in urlsplit(url).fragment.split("&"):
        if not token:
            continue
        key, separator, value = token.partition("=")
        if not separator or key in result or key not in {"in", "out", "hide", "ntf"}:
            raise ValueError("Unsupported service selection URL parameter")
        if key in {"in", "out"}:
            values = [unquote(part) for part in value.split("+")]
            if not values or any(not part or part != part.strip() or any(ord(c)<32 for c in part) for part in values):
                raise ValueError("Malformed literal service selection")
            result[key] = values
        else:
            if value not in {"0", "1"}:
                raise ValueError("Unsupported service parser option")
            result[key] = value
    return result


def prepare_service_filters(source, body):
    if not isinstance(body, str) or not body.strip():
        raise ValueError("Empty service source")
    spec = source.get("service_selection")
    if not isinstance(spec, dict) or not {"allowed_input_policies", "allowed_selected_types"} <= set(spec) or set(spec)-{"allowed_input_policies", "allowed_selected_types", "kop_drop_options"}:
        raise ValueError("Service source needs a reviewed policy and type contract")
    allowed_policies = spec["allowed_input_policies"]
    allowed_types = spec["allowed_selected_types"]
    drop_options = spec.get("kop_drop_options", [])
    if not isinstance(drop_options,list) or set(drop_options)-{"no-resolve", "extended-matching"}:
        raise ValueError("Unreviewed KOP compatibility option removal")
    if not isinstance(allowed_policies, list) or not isinstance(allowed_types, list) or not allowed_types:
        raise ValueError("Invalid service policy/type contract")
    if any(not isinstance(x,str) or not x or x!=x.strip() for x in [*allowed_policies,*allowed_types]):
        raise ValueError("Invalid service contract name")
    params = _parameters(source["url"])
    active = []
    for number, line in enumerate(body.lstrip("\ufeff").splitlines(), 1):
        value = line.strip()
        if value and not value.startswith(("#", ";", "//")):
            fields = [part.strip() for part in value.split(",")]
            if len(fields)>2 and fields[2].lower().split("=",1)[0] not in FLAG_OPTIONS | VALUE_OPTIONS:
                if fields[2] not in allowed_policies:
                    raise ValueError("Service source policy changed; review before publication")
            active.append((number,value))
    out_counts = {key: sum(key in line for _,line in active) for key in params.get("out", [])}
    retained = [(number,line) for number,line in active if not any(key in line for key in params.get("out", []))]
    if not retained:
        raise ValueError("Service selection removed every row")
    # Parse one row at a time so unsupported rules cannot disappear as comments.
    model = []
    policy_source = dict(source, source_format="qx")
    for number,line in retained:
        parsed,_ = parse_filters(policy_source,line)
        if len(parsed)!=1:
            raise ValueError("Service source row did not produce exactly one rule")
        model.append((number,parsed[0]))
    dropped = Counter(option for _,rule in model for option in rule.options if option in drop_options)
    model = [(number,replace(rule,options=tuple(option for option in rule.options if option not in drop_options))) for number,rule in model]
    in_counts = {key:sum(key in rule.render() for _,rule in model) for key in params.get("in", [])}
    if params.get("in"):
        model = [(number,rule) for number,rule in model if any(key in rule.render() for key in params["in"])]
    if not model:
        raise ValueError("Service selection produced no rules")
    if any(rule.kind not in allowed_types for _,rule in model):
        raise ValueError("Service source match type changed; review before publication")
    rendered = "\n".join(rule.render() for _,rule in model)+"\n"
    report = {"schema_version":1,"kind":"reviewed-service-filter","source_sha256":hashlib.sha256(body.encode()).hexdigest(),
              "input_rules":len(active),"selected_rules":len(model),"out_key_counts":out_counts,"in_key_counts":in_counts,
              "selected_type_counts":dict(sorted(Counter(rule.kind for _,rule in model).items())),
              "allowed_input_policies":allowed_policies,"output_sha256":hashlib.sha256(rendered.encode()).hexdigest(),
              "kop_compatibility_dropped_options":dict(sorted(dropped.items())),
              "selection":"KOP literal out on original rows, then literal in on normalized rows; force selected service policy"}
    return rendered,report
