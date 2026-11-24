"""Select the Bilibili app's home feed, public dynamic feeds and live promotions."""
from __future__ import annotations

import hashlib
import json
import re


REPO = "https://github.com/Biliverse/ADBlock"
API_PATH = "/repos/Biliverse/ADBlock/releases/latest"
MODULE = "BiliBili.ADBlock.snippet"
SCRIPT = "response.bundle.js"
SOURCE_URL = f"{REPO}/releases/latest/download/{MODULE}"
HOSTS = ("app.bilibili.com", "app.biliapi.net", "grpc.biliapi.net", "api.live.bilibili.com")


def select_release(raw: bytes | dict) -> tuple[str, dict]:
    release = raw if isinstance(raw, dict) else json.loads(raw)
    tag = release.get("tag_name", "")
    if (not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag)
            or release.get("draft") is not False or release.get("prerelease") is not False
            or release.get("html_url") != f"{REPO}/releases/tag/{tag}"):
        raise ValueError("Expected a stable Biliverse/ADBlock release")
    selected = {}
    for asset in release["assets"]:
        name = asset["name"]
        if name not in (MODULE, SCRIPT):
            continue
        if (name in selected or asset.get("browser_download_url") != f"{REPO}/releases/download/{tag}/{name}"
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", asset.get("digest") or "")
                or type(asset.get("size")) is not int or asset["size"] < 1):
            raise ValueError(f"Unexpected Biliverse release asset: {name}")
        selected[name] = asset
    if selected.keys() != {MODULE, SCRIPT}:
        raise ValueError("Biliverse release is missing its native QX module or response script")
    return tag, selected


def verify_asset(asset: dict, raw: bytes) -> None:
    if len(raw) != asset["size"] or "sha256:" + hashlib.sha256(raw).hexdigest() != asset["digest"]:
        raise ValueError(f"Content differs from the published release digest: {asset['name']}")


# Require each reviewed upstream rule to be present before narrowing its scope.
# End anchors keep searches, story videos and other paths away from this module.
REVIEWED_MATCHERS = (
    (r"^https?:\/\/app\.bili(bili\.com|api\.net)\/x\/v2\/(splash\/(brand\/list|event\/list2|list|show)|feed\/index(\/(relate\/)?story)?|search\/square)",
     r"^https?:\/\/app\.bili(?:bili\.com|api\.net)\/x\/v2\/feed\/index(?:\?|$)"),
    (r"^https?:\/\/(grpc|app)\.bili(bili\.com|api\.net)\/bilibili\.app\.dynamic\.v2\.Dynamic\/Dyn(All|Video)(Personal)?$",
     r"^https?:\/\/(?:grpc\.biliapi\.net|app\.bili(?:bili\.com|api\.net))\/bilibili\.app\.dynamic\.v2\.Dynamic\/Dyn(?:All|Video)$"),
    (r"^https?:\/\/api\.live\.bilibili\.com\/xlive\/(app-room\/v1\/index\/getInfoByRoom|app-interface\/v2\/(index\/feed|room\/recList))",
     r"^https?:\/\/api\.live\.bilibili\.com\/xlive\/(?:app-room\/v1\/index\/getInfoByRoom|app-interface\/v2\/(?:index\/feed|room\/recList))(?:\?|$)"),
)


def adapt_bilibili(module: str, tag: str) -> tuple[str, dict]:
    script_url = f"{REPO}/releases/download/{tag}/{SCRIPT}"
    lines = [line.strip() for line in module.splitlines()]
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) or f"#!version = {tag[1:]}" not in lines:
        raise ValueError("Biliverse module version differs from the release")
    hostname_rows = [line.split("=", 1)[1] for line in lines if line.startswith("hostname =")]
    if len(hostname_rows) != 1 or not set(HOSTS) <= {h.strip() for h in hostname_rows[0].split(",")}:
        raise ValueError("Review changed Biliverse MITM hostnames")
    selected = []
    for original, narrowed in REVIEWED_MATCHERS:
        handler = f" url script-response-body {script_url}"
        if lines.count(original + handler) != 1:
            raise ValueError("Review changed Biliverse response matcher or script: " + original)
        selected.append(narrowed + handler)
    selected.append("hostname = " + ", ".join(HOSTS))
    return "\n".join(selected) + "\n", {
        "release": tag, "module_url": f"{REPO}/releases/download/{tag}/{MODULE}",
        "selected_upstream_matchers": [original for original, _ in REVIEWED_MATCHERS],
        "scope": "App home feed, public dynamic feeds and live promotions",
    }
