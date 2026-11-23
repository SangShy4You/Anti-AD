"""Adapt the two audited RuleGo ad modules to native QX remote resources.

This is intentionally not a general Surge converter. Unsupported active data
stops the update rather than being silently omitted. No I/O or script execution
is performed here. HTTP header conversion is restricted to the reviewed,
same-host googlevideo request-target edit; it never changes it into a redirect.
"""
from __future__ import annotations

from collections import Counter
import re
from urllib.parse import urlsplit


YOUTUBE_AUTHOR_QX = "https://raw.githubusercontent.com/app2smile/rules/master/module/youtube-qx.conf"
YOUTUBE_SCRIPT = "https://raw.githubusercontent.com/app2smile/rules/master/js/youtube.js"
YOUTUBE_SCRIPT_PATTERN = r"^https:\/\/youtubei\.googleapis\.com\/youtubei\/v1\/(browse|next)\?"
YOUTUBE_UDP_RULE = "AND,((PROTOCOL,UDP),(DEST-PORT,443),(DOMAIN-SUFFIX,googlevideo.com)),REJECT-NO-DROP"
YOUTUBE_HEADER_PATTERN = r"(^https?:\/\/[\w-]+\.googlevideo\.com\/(?!dclk_video_ads).+?)&ctier=L(&.+?),ctier,(.+)"
YOUTUBE_HEADER_REPLACEMENT = "$1$2$3"
# QX represents the request line and headers in a CRLF-separated string. The
# URL gate remains the exact upstream full-URL regex. This second regex edits
# just the request target, preserving method, host, HTTP version and headers.
QX_YOUTUBE_HEADER_MATCH = r"^(\S+\s+\S+?)&ctier=L(&\S+?),ctier,(\S+\s+HTTP/[0-9.]+)(\r\n)"
QX_YOUTUBE_HEADER_REPLACEMENT = r"$1$2$3$4"

EVIDENCE = {
    "surge_header_semantics": "https://manual.nssurge.com/http/url-rewrite.html",
    "qx_request_header": "https://raw.githubusercontent.com/crossutility/Quantumult-X/master/sample.conf",
    "qx_binary_body": "https://raw.githubusercontent.com/crossutility/Quantumult-X/master/sample-bytes-rewrite.js",
    "author_native_youtube": YOUTUBE_AUTHOR_QX,
}


def _kind(source):
    kind = source.get("surge_ad_kind")
    if kind is None:
        name = urlsplit(str(source.get("url", ""))).path.rsplit("/", 1)[-1]
        kind = {"Advertising.sgmodule": "advertising", "YouTubeAds.sgmodule": "youtube"}.get(name)
    if kind not in {"advertising", "youtube"}:
        raise ValueError("Only audited advertising/youtube Surge ad modules are supported")
    return kind


def _hosts(line, location):
    match = re.fullmatch(r"hostname\s*=\s*(.*)", line, re.I)
    if not match:
        raise ValueError(f"{location}: unsupported active MITM option")
    text = re.sub(r"^%APPEND%\s*,?\s*", "", match.group(1), flags=re.I)
    result = []
    for entry in text.split(","):
        entry = entry.strip()
        if not entry or re.search(r"[\s/\\=]", entry) or entry == "%APPEND%":
            raise ValueError(f"{location}: invalid MITM hostname")
        result.append(entry)
    return result


def _youtube_script(line, location):
    match = re.fullmatch(r"youtube-proto\s*=\s*(.*)", line)
    if not match:
        raise ValueError(f"{location}: unsupported script declaration")
    fields = {}
    for token in match.group(1).split(","):
        key, separator, value = token.strip().partition("=")
        if not separator or not value or key in fields:
            raise ValueError(f"{location}: malformed/duplicate script parameter")
        fields[key] = value
    required = {"type": "http-response", "pattern": YOUTUBE_SCRIPT_PATTERN,
                "requires-body": "1", "binary-body-mode": "1", "max-size": "2097152",
                "script-path": YOUTUBE_SCRIPT}
    if fields != required:
        raise ValueError(f"{location}: audited YouTube script parameters changed; review required")
    return fields


def adapt_surge_ad_source(source, body):
    """Return ``(flat_qx_text, report)`` for an audited Surge ad source.

    Metadata ``surge_ad_kind`` accepts ``advertising`` or ``youtube``; the
    original RuleGo filename can also identify the kind. For YouTube,
    ``youtube_script_mode='author-native'`` leaves script selection to the
    author's separate native QX resource and records that required source.
    Default ``include`` converts the audited binary script hook directly.

    The UDP/443 logical rule is always reported as an explicit carry item.
    It is never widened into a new global UDP drop rule by this adapter.
    """
    sid = source.get("id")
    if not isinstance(sid, str) or not sid or any(char in sid for char in "\r\n"):
        raise ValueError("Source id is required")
    if not isinstance(body, str) or not body.strip() or re.match(r"\s*(?:<!doctype|<html)", body, re.I):
        raise ValueError(f"{sid}: empty or HTML source")
    kind = _kind(source)
    script_mode = source.get("youtube_script_mode", "include")
    if script_mode not in {"include", "author-native"}:
        raise ValueError("Invalid YouTube script selection mode")
    report = {
        "source": sid, "kind": kind,
        "validation": "Static audited format conversion only; no iOS QX execution test.",
        "evidence": EVIDENCE,
        "converted": [], "explicit_carry": [], "script_selection": [],
        "required_sources": [], "hostnames": [],
    }
    section = ""
    sections = set()
    output, hosts = [], []
    counts = Counter()
    for number, raw in enumerate(body.lstrip("\ufeff").splitlines(), 1):
        line = raw.strip()
        location = f"{sid}:{number}"
        if not line:
            continue
        if line.lower().startswith("#!include"):
            raise ValueError(f"{location}: includes require a separate reviewed dependency")
        if line.startswith(("#", ";", "//")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            if section not in {"rule", "url rewrite", "script", "mitm"}:
                raise ValueError(f"{location}: unsupported section {line}")
            sections.add(section)
            continue
        counts["input_active_records"] += 1
        if section == "rule":
            if kind != "youtube" or line != YOUTUBE_UDP_RULE:
                raise ValueError(f"{location}: unsupported route/logical rule")
            report["explicit_carry"].append({
                "line": number, "rule": line, "converted": False,
                "reason": "A protocol/port/domain conjunction cannot be widened into a global UDP drop. Preserve the existing private profile UDP policy separately; the original KOP parser also does not directly convert logical rules.",
            })
            counts["logical_rules_recorded"] += 1
        elif section == "url rewrite":
            fields = line.rsplit(None, 2)
            if len(fields) != 3:
                raise ValueError(f"{location}: malformed Surge URL rewrite")
            pattern, replacement, action = fields
            if action.lower() == "reject" and replacement in {"-", "_"}:
                native = pattern + " url reject"
                counts["reject_rules"] += 1
            elif (kind == "youtube" and action == "header"
                  and pattern == YOUTUBE_HEADER_PATTERN
                  and replacement == YOUTUBE_HEADER_REPLACEMENT):
                native = (pattern + " url request-header " + QX_YOUTUBE_HEADER_MATCH
                          + " request-header " + QX_YOUTUBE_HEADER_REPLACEMENT)
                counts["request_header_rules"] += 1
            else:
                raise ValueError(f"{location}: unaudited URL rewrite action or header expression")
            output.append(native)
            report["converted"].append({"line": number, "original": line, "native": native})
        elif section == "script":
            if kind != "youtube":
                raise ValueError(f"{location}: Advertising module contains a new script")
            fields = _youtube_script(line, location)
            counts["audited_script_hooks"] += 1
            selection = {"line": number, "url": fields["script-path"],
                         "binary_body": "Native QX bodyBytes support is documented and used by the author's QX resource.",
                         "surge_max_size": 2097152,
                         "max_size_note": "No unverified QX max-size key is emitted; use the author's native QX hook and native runtime limits.",
                         "mode": script_mode}
            if script_mode == "include":
                native = fields["pattern"] + " url script-response-body " + fields["script-path"]
                output.append(native)
                report["converted"].append({"line": number, "original": line, "native": native})
            else:
                report["required_sources"] = [YOUTUBE_AUTHOR_QX]
                selection["reason"] = "Use the single hook in the separately selected author's native QX resource; do not execute both overlapping hooks."
            report["script_selection"].append(selection)
        elif section == "mitm":
            hosts.extend(_hosts(line, location))
            counts["mitm_declarations"] += 1
        else:
            raise ValueError(f"{location}: active content outside supported sections")
    if not {"url rewrite", "mitm"}.issubset(sections) or not output or not hosts:
        raise ValueError(f"{sid}: incomplete audited ad module")
    if kind == "youtube" and (counts["request_header_rules"] != 1
                              or counts["audited_script_hooks"] != 1
                              or counts["logical_rules_recorded"] != 1):
        raise ValueError(f"{sid}: expected YouTube header/script/logical-rule evidence changed")
    report["hostnames"] = list(dict.fromkeys(hosts))
    counts["output_rewrite_rules"] = len(output)
    report["counts"] = dict(sorted(counts.items()))
    result = "# Native QX adaptation of audited RuleGo ad module: " + sid + "\n"
    result += "\n".join(output) + "\nhostname = " + ", ".join(report["hostnames"]) + "\n"
    return result, report
