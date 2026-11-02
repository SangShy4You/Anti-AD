"""Extract only previously audited whole-host rejects from rewrite data.

This module never executes scripts or promotes arbitrary URL patterns into
domain blocks. The allowlist is reviewed code: additions require a code change.
"""

from __future__ import annotations

import re


class ExtractionError(ValueError):
    """The source no longer proves every audited whole-host rejection."""


# Native domain-list notation preserves exact hosts and children-only matches.
# In particular, a leading dot must never become '+.' or DOMAIN-SUFFIX.
AUDITED_RULES = (
    ("fc-video.cdn.bcebos.com", r"^https?:\/\/fc-video\.cdn\.bcebos\.com"),
    ("api.htp.ad-scope.com.cn", r"^https?:\/\/api\.htp\.ad-scope\.com\.cn.*"),
    ("sdk1xyajs.data.kuiniuca.com", r"^https?:\/\/sdk1xyajs\.data\.kuiniuca\.com"),
    ("stat.peopleapp.com", r"^https?:\/\/stat\.peopleapp\.com\/"),
    ("adapi.izuiyou.com", r"^https?:\/\/adapi\.izuiyou\.com\/"),
    (".kingsoft-office-service.com", r"^https?:\/\/.+?\.kingsoft-office-service\.com"),
    (".pglstatp-toutiao.com", r"^https?:\/\/.+\.pglstatp-toutiao\.com"),
)

_URL_RULE = re.compile(
    r"(?P<pattern>\S+)[ \t]+url[ \t]+(?P<action>\S+)"
    r"(?:[ \t]+(?:\#|//).*)?\Z"
)


def audit_rule_source(text: str) -> dict:
    """Require the exact reviewed patterns with plain reject, then report evidence.

    URL-path restrictions, response stubs, scripts, redirects and newly added
    domains cannot satisfy the allowlist. A missing/changed reviewed expression
    raises instead of silently publishing a shorter or more aggressive list.
    """
    if not isinstance(text, str) or not text.strip() or "\x00" in text:
        raise ExtractionError("Rewrite source must be nonempty text without NUL bytes")
    evidence = {expression: [] for _, expression in AUDITED_RULES}
    for number, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        match = _URL_RULE.fullmatch(line)
        if match is None or match["action"] != "reject":
            continue
        expression = match["pattern"]
        if expression in evidence:
            evidence[expression].append({"line": number, "rule": line})
    missing = [pattern for pattern, expression in AUDITED_RULES if not evidence[expression]]
    if missing:
        raise ExtractionError(
            "Missing audited whole-host plain reject evidence for: " + ", ".join(missing)
            + "; previous published rules must be preserved")
    return {
        "schema_version": 1,
        "format": "domain_text",
        "count": len(AUDITED_RULES),
        "entries": [
            {"domain_pattern": pattern,
             "scope": "subdomains-only" if pattern.startswith(".") else "exact-host",
             "source_expression": expression,
             "evidence": evidence[expression]}
            for pattern, expression in AUDITED_RULES
        ],
        "limitations": [
            "Only reviewed whole-host plain URL rejects are represented.",
            "A network REJECT does not reproduce an HTTP rejection status/body.",
            "Path-specific rules, response stubs, JavaScript and MITM are not converted.",
        ],
    }


def extract_rule_source(text: str) -> str:
    """Return deterministic native domain text for source_format=domain_text."""
    audit = audit_rule_source(text)
    return ("# Audited whole-host plain rejects; URL scripts were not executed.\n"
            + "\n".join(entry["domain_pattern"] for entry in audit["entries"]) + "\n")
