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
import struct
import zlib
import sys
from urllib.parse import quote, urlsplit, urlunsplit
import urllib.request

if __package__:
    from . import update
    from .qx_filters import compile_filters
    from .qx_rewrites import compile_rewrites
    from .qx_dependencies import pin_url, resolve_ref
    from .qx_surge_ads import adapt_surge_ad_source
    from .qx_web_ads import patch_limbo_entry
    from .qx_youtube import prepare_response_script
    from .qx_extra_filters import extract_fmz_ad_filters
    from .qx_mixed_guard import validate_mixed_reference
    from .qx_profile_dedup import deduplicate_profile
    from .qx_filter_partition import partition_ordered_filters
    from .qx_service_filters import prepare_service_filters
else:
    import update
    from qx_filters import compile_filters
    from qx_rewrites import compile_rewrites
    from qx_dependencies import pin_url, resolve_ref
    from qx_surge_ads import adapt_surge_ad_source
    from qx_web_ads import patch_limbo_entry
    from qx_youtube import prepare_response_script
    from qx_extra_filters import extract_fmz_ad_filters
    from qx_mixed_guard import validate_mixed_reference
    from qx_profile_dedup import deduplicate_profile
    from qx_filter_partition import partition_ordered_filters
    from qx_service_filters import prepare_service_filters

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "rules/quantumultx/"
PUBLIC = "https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/"
IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,100}\Z")
GENERATOR_MODULES = ("qx_build.py", "qx_filters.py", "qx_rewrites.py", "qx_dependencies.py", "qx_surge_ads.py", "qx_web_ads.py", "qx_extra_filters.py", "qx_mixed_guard.py", "qx_profile_dedup.py", "qx_filter_partition.py", "qx_service_filters.py", "qx_youtube.py")


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def transparent_png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0" * 5)) + chunk(b"IEND", b""))


def check_javascript(raw, url):
    result = subprocess.run(["node", "--check"], input=raw, capture_output=True,
                            timeout=15, creationflags=0x08000000 if sys.platform == "win32" else 0)
    if result.returncode:
        raise ValueError("JavaScript syntax check failed: " + url)


def fetch_binary_url(url, *, browser=False):
    if browser:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "cdn.jsdelivr.net" or not parsed.path.startswith("/gh/limbopro/Adblock4limbo@"):
            raise ValueError("Unreviewed browser asset URL")
    else:
        url = download_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "Anti-AD-QX-assets/1", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(5 * 1024 * 1024 + 1)
        mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if response.status != 200 or not raw or len(raw) > 5 * 1024 * 1024:
            raise ValueError("Invalid static asset download")
    if browser and mime not in {"application/javascript", "text/javascript"}:
        raise ValueError("Browser script is not served with a JavaScript MIME type")
    return raw, mime


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
        if source.get("local_path"):
            if not source["local_path"].startswith("config/"):
                raise ValueError("Local reviewed rules must be inside config/")
            local = update._path(root, source["local_path"])
            try:
                local.resolve().relative_to((root / "config").resolve())
            except ValueError as exc:
                raise ValueError("Local reviewed rules escape config/") from exc
            raw = local.read_bytes()
        else:
            raw = ((Path(offline_dir) / (source["id"] + ".txt")).read_bytes()
                   if offline_dir else (fetcher or update.fetch_url)(url))
        return source["id"], raw, update.validate_body(raw)

    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(obtain, active))
    raw_bodies = {name: raw for name, raw, _ in fetched}
    bodies = {name: body for name, _, body in fetched}
    mixed_guards = []
    for spec in config.get("validation_sources", []):
        guard_url = download_url(spec["url"])
        reused = next((raw_bodies[s["id"]] for s in active if s["url"] == spec["url"]), None)
        if reused is not None:
            guard_raw = reused
        elif offline_dir:
            if not IDENTIFIER.fullmatch(spec["id"]):
                raise ValueError("Invalid validation source ID")
            guard_raw = (Path(offline_dir) / (spec["id"] + ".txt")).read_bytes()
        else:
            guard_raw = (fetcher or update.fetch_url)(guard_url)
        mixed_guards.append({"id": spec["id"], "url": spec["url"],
                             **validate_mixed_reference(update.validate_body(guard_raw), spec)})
    adaptations = {}
    for source in active:
        if source.get("source_format") == "surge_ad_module":
            bodies[source["id"]], adaptations[source["id"]] = adapt_surge_ad_source(source, bodies[source["id"]])
        elif source.get("source_format") == "fmz_ad_filter_tail":
            bodies[source["id"]], adaptations[source["id"]] = extract_fmz_ad_filters(bodies[source["id"]])
        elif source.get("source_format") == "service_filter":
            bodies[source["id"]], adaptations[source["id"]] = prepare_service_filters(source, bodies[source["id"]])
    products, filter_reports, rewrite_reports = {}, {}, {}
    for output, selection in config["products"].items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*\.(?:list|conf)", output):
            raise ValueError("Unsafe product filename: " + output)
        selected = [next(s for s in active if s["id"] == name) for name in selection["sources"]]
        if selection["kind"] == "filter":
            prepared = [dict(s, source_format="qx") if s.get("source_format") in {"fmz_ad_filter_tail", "service_filter"} else s for s in selected]
            text, report = compile_filters(prepared, bodies, overrides=selection.get("overrides", []))
            filter_reports[output] = report
        elif selection["kind"] == "rewrite":
            for source in selected:
                for required in adaptations.get(source["id"], {}).get("required_sources", []):
                    if required not in {s["url"] for s in selected}:
                        raise ValueError(f"{output}: missing adapted source dependency {required}")
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

    partition_reports, partition_imports = {}, {}
    partition_specs = config.get("filter_partitions", {})
    if not isinstance(partition_specs, dict):
        raise ValueError("Filter partitions must map compiled filter products to ordered specifications")
    for output, specs in partition_specs.items():
        if output not in filter_reports:
            raise ValueError("Filter partition source is not a compiled filter product")
        derived, imports, partition_report = partition_ordered_filters(products[PREFIX + output].decode("utf-8"), specs)
        if any(PREFIX + name in products for name in derived):
            raise ValueError("Filter partition output collides with an existing product")
        products.update({PREFIX + name: text.encode("utf-8") for name, text in derived.items()})
        partition_reports[output] = partition_report
        partition_imports[output] = imports

    profile_dedup = (deduplicate_profile(products, rewrite_reports, config["profile_rewrite_order"])
                     if config.get("profile_rewrite_order") else [])
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
    pinned_data = {item["url"]: pin_url(item["url"], resolve) for item in config.get("data_dependencies", [])}
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
            if patch.get("mode") == "limbo-browser":
                text, record["browser_patch"] = patch_limbo_entry(text, pinned[url])
                record["patch_applied"] = True
            elif patch.get("mode") == "youtube-response":
                text, record["youtube_patch"] = prepare_response_script(text, pinned[url])
                record["patch_applied"] = True
            else:
                replacement = pinned_data[patch["replacement_url"]] if "replacement_url" in patch else patch["new"]
                if text.count(patch["old"]) == 1:
                    text = text.replace(patch["old"], replacement)
                    record["patch_applied"] = True
                elif text.count(patch["old"]) == 0 and text.count(replacement) == 1:
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
        pinned_resource = pinned_data[url]
        fetch_url = download_url(pinned_resource)
        raw = ((Path(dependency_dir) / (digest(fetch_url.encode()) + ".data")).read_bytes()
               if dependency_dir else (fetch_binary_url(fetch_url)[0] if resource["kind"] == "jpeg" else (fetcher or update.fetch_url)(fetch_url)))
        if resource["kind"] == "json":
            json.loads(update.validate_body(raw))
        elif resource["kind"] == "jpeg":
            if not raw.startswith(b"\xff\xd8\xff") or not raw.endswith(b"\xff\xd9"):
                raise ValueError("Invalid reviewed JPEG resource")
        else:
            raise ValueError("Unknown reviewed static resource format")
        resources.append({"url": url, "pinned_url": pinned_resource, "bytes": len(raw), "sha256": digest(raw)})
        replacements[url] = pinned_resource
    browser_assets = []
    for url in sorted({u for item in dependencies for u in item.get("browser_patch", {}).get("browser_assets", [])}):
        if dependency_dir:
            raw = (Path(dependency_dir) / (digest(url.encode()) + ".browser")).read_bytes()
            mime = "application/javascript"
        else:
            raw, mime = fetch_binary_url(url, browser=True)
        update.validate_body(raw)
        check_javascript(raw, url)
        browser_assets.append({"url": url, "bytes": len(raw), "sha256": digest(raw), "content_type": mime})
    for name in rewrite_reports:
        path = PREFIX + name
        text = products[path].decode("utf-8")
        for original, replacement in sorted(replacements.items(), key=lambda pair: -len(pair[0])):
            text = text.replace(" " + original + "\n", " " + replacement + "\n")
        products[path] = text.encode("utf-8")
    products.update(patched_products)
    if any(patch.get("transparent_asset") for patch in patches.values()):
        products[PREFIX + "assets/transparent.png"] = transparent_png()

    imports = ["# 合并到现有配置的同名段；不是完整 VPN 配置，勿覆盖节点、DNS 或证书。", "[filter_remote]"]
    for output, selection in config["products"].items():
        if selection["kind"] == "filter":
            if selection.get("import", True) is False:
                continue
            enabled = str(selection.get("default_enabled", True)).lower()
            if output in partition_imports:
                for item in partition_imports[output]:
                    force = f", force-policy={item['force_policy']}" if item["force_policy"] else ""
                    imports.append(f"{PUBLIC}{PREFIX}{item['output']}, tag={item['name']}{force}, update-interval=86400, opt-parser=false, enabled={enabled}")
            else:
                policy = selection.get("import_force_policy")
                if policy is not None and (not isinstance(policy,str) or not policy.strip() or policy != policy.strip() or any(c in policy for c in ",\r\n")):
                    raise ValueError("Invalid reviewed filter import policy")
                force = f", force-policy={policy}" if policy is not None else ""
                imports.append(f"{PUBLIC}{PREFIX}{output}, tag={selection['name']}{force}, update-interval=86400, opt-parser=false, enabled={enabled}")
    imports += ["", "[rewrite_remote]"]
    rewrite_outputs = [output for output, selection in config["products"].items() if selection["kind"] == "rewrite"]
    reviewed_order = config.get("profile_rewrite_order") or []
    # The same first-match order drives cross-product deduplication and imports.
    # Unlisted optional resources remain present after the reviewed active set;
    # configurations without an order retain their original product ordering.
    rewrite_import_order = [*reviewed_order, *(output for output in rewrite_outputs if output not in reviewed_order)]
    for output in rewrite_import_order:
        selection = config["products"][output]
        enabled = str(selection.get("default_enabled", True)).lower()
        imports.append(f"{PUBLIC}{PREFIX}{output}, tag={selection['name']}, update-interval=86400, opt-parser=false, enabled={enabled}")
    products[PREFIX + "import.snippet"] = ("\n".join(imports) + "\n").encode("utf-8")
    report = {
        "schema_version": 1,
        "scope": config["scope"],
        "validation": "static structure and all referenced script downloads; not an iOS Quantumult X execution test",
        "config_sha256": digest(config_raw),
        "generator_sha256": digest(b"\n".join((root / "scripts" / name).read_bytes() for name in GENERATOR_MODULES)),
        "sources": [{"id": s["id"], "url": s["url"], "bytes": len(raw_bodies[s["id"]]),
                     "sha256": digest(raw_bodies[s["id"]]), "name": s["name"],
                     "license": s.get("license", "See third-party notices")} for s in active],
        "filters": filter_reports, "rewrites": rewrite_reports,
        "filter_partitions": partition_reports,
        "script_dependencies": dependencies,
        "data_dependencies": resources,
        "browser_asset_dependencies": browser_assets,
        "source_adaptations": adaptations,
        "mixed_remote_reference_guards": mixed_guards,
        "profile_rewrite_deduplication": profile_dedup,
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
