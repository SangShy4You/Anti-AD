"""Build native Quantumult X resources from reviewed public raw sources.

This is a static compiler, not a Quantumult X runtime. Downloaded JavaScript is
read as data and hashed; it is never executed. Publication is all-or-nothing.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlsplit, urlunsplit

if __package__:
    from . import update
    from .qx_filters import compile_filters
    from .qx_rewrites import compile_rewrites
    from .qx_dependencies import pin_url, resolve_ref
else:
    import update
    from qx_filters import compile_filters
    from qx_rewrites import compile_rewrites
    from qx_dependencies import pin_url, resolve_ref

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "rules/quantumultx/"
PUBLIC = "https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/"
IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,100}\Z")


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def check_javascript(raw, url):
    result = subprocess.run(["node", "--check"], input=raw, capture_output=True,
                            timeout=15, creationflags=0x08000000 if sys.platform == "win32" else 0)
    if result.returncode:
        raise ValueError("JavaScript syntax check failed: " + url)


def download_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"raw.githubusercontent.com", "gist.githubusercontent.com", "github.com"}:
        raise ValueError("Only explicit HTTPS GitHub raw sources are accepted: " + url)
    if parsed.username or parsed.password:
        raise ValueError("A raw URL must not contain credentials")
    if parsed.hostname == "github.com":
        parts = parsed.path.split("/")
        if len(parts) < 6 or parts[3] != "raw":
            raise ValueError("GitHub browser pages cannot be used as raw script sources")
        parsed = parsed._replace(netloc="raw.githubusercontent.com", path="/" + "/".join(parts[1:3] + parts[4:]))
    if not parsed.path or len(parsed.path.split("/")) < 5:
        raise ValueError("Incomplete GitHub raw source URL")
    if parsed.hostname == "gist.githubusercontent.com" and "/raw/" not in parsed.path:
        raise ValueError("Gist script must point to its raw content")
    return urlunsplit(parsed._replace(path=quote(parsed.path, safe="/%:@+"), fragment=""))


def build(root=ROOT, *, offline_dir=None, dependency_dir=None, fetcher=None, resolver=None):
    root = Path(root).resolve()
    config_raw = (root / "config/qx-sources.json").read_bytes()
    config = json.loads(config_raw)
    sources = config["sources"]
    identifiers = [s["id"] for s in sources]
    if len(set(identifiers)) != len(identifiers) or not all(IDENTIFIER.fullmatch(x) for x in identifiers):
        raise ValueError("Invalid or duplicate source identifiers")
    active = [s for s in sources if s.get("enabled", True)]

    def obtain(source):
        url = download_url(source["url"])
        raw = ((Path(offline_dir) / (source["id"] + ".txt")).read_bytes()
               if offline_dir else (fetcher or update.fetch_url)(url))
        return source["id"], raw, update.validate_body(raw)

    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(obtain, active))
    raw_bodies = {name: raw for name, raw, _ in fetched}
    bodies = {name: body for name, _, body in fetched}
    products, filter_reports, rewrite_reports = {}, {}, {}
    for output, selection in config["products"].items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*\.(?:list|conf)", output):
            raise ValueError("Unsafe product filename: " + output)
        selected = [next(s for s in active if s["id"] == name) for name in selection["sources"]]
        if selection["kind"] == "filter":
            text, report = compile_filters(selected, bodies, overrides=selection.get("overrides", []))
            filter_reports[output] = report
        elif selection["kind"] == "rewrite":
            text, report = compile_rewrites(selected, bodies)
            for key in ("local_script_references", "local_data_references", "hostname_conflicts"):
                if report.get(key):
                    raise ValueError(f"{output}: unresolved {key}; review required before publication")
            additions = selection.get("additional_hostnames", {})
            for hostname, reason in additions.items():
                if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", hostname) or not reason:
                    raise ValueError("Invalid reviewed hostname addition")
                text = re.sub(r"(?m)^hostname\s*=\s*", "hostname = " + hostname + ", ", text, count=1)
            report["reviewed_hostname_additions"] = additions
            rewrite_reports[output] = report
        else:
            raise ValueError("Unknown product kind")
        for item in report["sources"]:
            if item["id"] == "personal_overrides":
                continue
            minimum = next(s for s in selected if s["id"] == item["id"]).get("min_rules", 1)
            if type(minimum) is not int or minimum < 1 or item.get("input_rules", 0) < minimum:
                raise ValueError(f"{item['id']}: rule count below its reviewed minimum {minimum}")
        products[PREFIX + output] = text.encode("utf-8")

    script_urls = sorted({url for report in rewrite_reports.values() for url in report["script_urls"]})
    approved_data = {item["url"] for item in config.get("data_dependencies", [])}
    for report in rewrite_reports.values():
        for rule in report["rules"]:
            if (rule["action"] in {"302", "307"}
                    and urlsplit(rule["argument"]).hostname in {"raw.githubusercontent.com", "gist.githubusercontent.com", "github.com"}
                    and rule["argument"] not in approved_data):
                raise ValueError("New GitHub redirect data dependency needs review: " + rule["argument"])
    approved = set(config["approved_script_urls"])
    unknown = set(script_urls) - approved
    if unknown:
        raise ValueError("New script references need review before publication: " + ", ".join(sorted(unknown)))

    resolved = {}
    def resolve(key):
        if key not in resolved:
            resolved[key] = (resolver or resolve_ref)(key)
        return resolved[key]
    pinned = {url: pin_url(url, resolve) for url in script_urls}
    patches = config.get("script_patches", {})
    patched_products = {}

    def read_script(url):
        fetch_url = download_url(pinned[url])
        cache_name = digest(fetch_url.encode()) + ".js"
        raw = ((Path(dependency_dir) / cache_name).read_bytes() if dependency_dir
               else (fetcher or update.fetch_url)(fetch_url))
        text = update.validate_body(raw)
        check_javascript(raw, fetch_url)
        if not re.search(r"\$(?:done|request|response|task|httpClient|prefs|persistentStore|environment)\b", text):
            raise ValueError("Script does not resemble a reviewed proxy script: " + fetch_url)
        record = {"url": url, "pinned_url": pinned[url], "fetch_url": fetch_url,
                  "bytes": len(raw), "sha256": digest(raw)}
        if url in patches:
            patch = patches[url]
            name = patch["filename"]
            if not re.fullmatch(r"[a-z][a-z0-9-]*\.js", name):
                raise ValueError("Unsafe script patch filename")
            if text.count(patch["old"]) == 1:
                text = text.replace(patch["old"], patch["new"])
                record["patch_applied"] = True
            elif text.count(patch["old"]) == 0 and text.count(patch["new"]) == 1:
                record["patch_applied"] = False
            else:
                raise ValueError("Upstream script changed around an audited patch; review needed: " + url)
            text = ("// Personal integration: " + patch["reason"] + "\n// Upstream: " + pinned[url] + "\n" + text)
            relative = PREFIX + "scripts/" + name
            payload = text.encode("utf-8")
            check_javascript(payload, "personal patch: " + name)
            original_parts = urlsplit(url)
            published = urlunsplit(urlsplit(PUBLIC + relative)._replace(
                query=original_parts.query, fragment=original_parts.fragment))
            record.update(published_url=published, published_sha256=digest(payload))
            return record, (relative, payload)
        return record, None

    with ThreadPoolExecutor(max_workers=6) as pool:
        read_dependencies = list(pool.map(read_script, script_urls))
    dependencies = []
    replacements = {}
    for record, product in read_dependencies:
        dependencies.append(record)
        replacements[record["url"]] = record.get("published_url", record["pinned_url"])
        if product:
            patched_products[product[0]] = product[1]
    resources = []
    for resource in config.get("data_dependencies", []):
        url = resource["url"]
        pinned_resource = pin_url(url, resolve)
        fetch_url = download_url(pinned_resource)
        raw = ((Path(dependency_dir) / (digest(fetch_url.encode()) + ".data")).read_bytes()
               if dependency_dir else (fetcher or update.fetch_url)(fetch_url))
        if resource["kind"] != "json":
            raise ValueError("Unknown reviewed static resource format")
        json.loads(update.validate_body(raw))
        resources.append({"url": url, "pinned_url": pinned_resource, "bytes": len(raw), "sha256": digest(raw)})
        replacements[url] = pinned_resource
    for name in rewrite_reports:
        path = PREFIX + name
        text = products[path].decode("utf-8")
        for original, replacement in sorted(replacements.items(), key=lambda pair: -len(pair[0])):
            text = text.replace(" " + original + "\n", " " + replacement + "\n")
        products[path] = text.encode("utf-8")
    products.update(patched_products)

    imports = ["# 合并到现有配置的同名段；不是完整 VPN 配置，勿覆盖节点、DNS 或证书。", "[filter_remote]"]
    for output, selection in config["products"].items():
        if selection["kind"] == "filter":
            enabled = str(selection.get("default_enabled", True)).lower()
            imports.append(f"{PUBLIC}{PREFIX}{output}, tag={selection['name']}, update-interval=86400, opt-parser=false, enabled={enabled}")
    imports += ["", "[rewrite_remote]"]
    for output, selection in config["products"].items():
        if selection["kind"] == "rewrite":
            enabled = str(selection.get("default_enabled", True)).lower()
            imports.append(f"{PUBLIC}{PREFIX}{output}, tag={selection['name']}, update-interval=86400, opt-parser=false, enabled={enabled}")
    products[PREFIX + "import.snippet"] = ("\n".join(imports) + "\n").encode("utf-8")
    report = {
        "schema_version": 1,
        "scope": config["scope"],
        "validation": "static structure and all referenced script downloads; not an iOS Quantumult X execution test",
        "config_sha256": digest(config_raw),
        "generator_sha256": digest(b"\n".join((root / "scripts" / name).read_bytes() for name in
                                              ("qx_build.py", "qx_filters.py", "qx_rewrites.py", "qx_dependencies.py"))),
        "sources": [{"id": s["id"], "url": s["url"], "bytes": len(raw_bodies[s["id"]]),
                     "sha256": digest(raw_bodies[s["id"]]), "name": s["name"],
                     "license": s.get("license", "See third-party notices")} for s in active],
        "filters": filter_reports, "rewrites": rewrite_reports,
        "script_dependencies": dependencies,
        "data_dependencies": resources,
        "resolved_refs": resolved,
        "script_policy": "Upstream JavaScript is pinned to full immutable commits; new script URLs require review. A documented local bug fix is maintained for Zhihu. Scripts are read and statically checked, never executed by this builder.",
        "omitted_candidates": config.get("omitted_candidates", []),
        "outputs": {path: {"sha256": digest(raw), "bytes": len(raw)} for path, raw in sorted(products.items())},
    }
    products[PREFIX + "manifest.json"] = dump(report).encode("utf-8")
    previous_path = root / PREFIX / "manifest.json"
    if previous_path.exists():
        previous = json.loads(previous_path.read_bytes())
        for path, metadata in previous.get("outputs", {}).items():
            if path not in products:
                if not path.startswith(PREFIX):
                    raise ValueError("An obsolete product is outside the QX directory")
                old = update._path(root, path, output=True)
                if old.exists() and digest(old.read_bytes()) != metadata["sha256"]:
                    raise ValueError("Obsolete QX product was manually edited: " + path)
                products[path] = None
    changed = update._publish(root, products)
    return {"changed_files": changed, "source_count": len(active), "script_count": len(dependencies),
            "products": {name: len(raw) for name, raw in products.items() if raw is not None}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-dir", type=Path)
    parser.add_argument("--dependency-dir", type=Path)
    parser.add_argument("--ref-map", type=Path, help="Reviewed local ref -> commit map; CI uses the official API")
    args = parser.parse_args()
    try:
        refs = json.loads(args.ref_map.read_bytes()) if args.ref_map else None
        print(dump(build(offline_dir=args.offline_dir, dependency_dir=args.dependency_dir,
                         resolver=refs.__getitem__ if refs is not None else None)))
        return 0
    except Exception as exc:
        print("QX build stopped; previously published files retained: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
