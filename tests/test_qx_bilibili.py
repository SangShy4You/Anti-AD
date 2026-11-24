"""Offline regression tests for the personal Bilibili cleanup resource."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unittest

from scripts.qx_bilibili import adapt_bilibili, select_release, verify_asset


FIXTURE = Path(__file__).with_name("fixtures") / "biliverse-v0.7.5.snippet"
TAG = "v0.7.5"
REPO = "https://github.com/Biliverse/ADBlock"
MODULE = "BiliBili.ADBlock.snippet"
SCRIPT = "response.bundle.js"
MODULE_BODY = FIXTURE.read_text(encoding="utf-8")


def sample_release():
    assets = []
    for name in (MODULE, SCRIPT):
        payload = name.encode()
        assets.append({
            "name": name, "size": len(payload),
            "browser_download_url": f"{REPO}/releases/download/{TAG}/{name}",
            "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
        })
    return {
        "tag_name": TAG, "html_url": f"{REPO}/releases/tag/{TAG}",
        "draft": False, "prerelease": False, "assets": assets,
    }


class BiliverseTests(unittest.TestCase):
    def test_only_expected_responses_reach_a_single_versioned_script(self):
        source, _ = adapt_bilibili(MODULE_BODY, TAG)
        host_line, = (line for line in source.splitlines() if line.startswith("hostname"))
        self.assertEqual({host.strip() for host in host_line.split("=")[1].split(",")},
                         {"app.bilibili.com", "app.biliapi.net", "grpc.biliapi.net", "api.live.bilibili.com"})
        rules = [line.split() for line in source.splitlines() if line.startswith("^")]
        self.assertEqual(len(rules), 3)
        for rule in rules:
            self.assertEqual(rule[1:], ["url", "script-response-body", f"{REPO}/releases/download/{TAG}/{SCRIPT}"])
        matchers = [re.compile(rule[0]) for rule in rules]
        def hits(url):
            return sum(bool(matcher.search(url)) for matcher in matchers)

        for domain in ("app.bilibili.com", "app.biliapi.net"):
            for query in ("", "?device=phone"):
                self.assertEqual(hits(f"https://{domain}/x/v2/feed/index{query}"), 1)
        for domain in ("grpc.biliapi.net", "app.bilibili.com", "app.biliapi.net"):
            for method in ("DynAll", "DynVideo"):
                self.assertEqual(hits(f"https://{domain}/bilibili.app.dynamic.v2.Dynamic/{method}"), 1)
        for endpoint in ("app-interface/v2/index/feed", "app-interface/v2/room/recList",
                         "app-room/v1/index/getInfoByRoom"):
            url = f"https://api.live.bilibili.com/xlive/{endpoint}"
            for query in ("", "?room_id=42"):
                self.assertEqual(hits(url + query), 1)
            self.assertEqual(hits(url + "V2"), 0)
        excluded = [
            "https://app.bilibili.com/x/v2/feed/index/story",
            "https://app.bilibili.com/x/v2/feed/index/relate/story",
            "https://app.bilibili.com/x/v2/splash/list",
            "https://app.bilibili.com/x/v2/search/square",
            "https://app.bilibili.com/x/v2/feed/indexExtra",
            "https://biliverse.github.io/api/ADBlock",
            "https://api.bilibili.com/x/web-interface/wbi/index/top/feed/rcmd?fresh_idx=1",
            "https://grpc.biliapi.net/bilibili.app.playurl.v1.PlayURL/PlayView",
            "https://grpc.biliapi.net/bilibili.app.view.v1.View/View",
            "https://grpc.biliapi.net/bilibili.app.dynamic.v2.Dynamic/DynAllPersonal",
            "https://grpc.biliapi.net/bilibili.app.dynamic.v2.Dynamic/DynVideoPersonal",
            "https://grpc.bilibili.com/bilibili.app.dynamic.v2.Dynamic/DynVideo",
            "https://app.bilibili.com.example/x/v2/feed/index",
        ]
        for url in excluded:
            with self.subTest(url=url):
                self.assertEqual(hits(url), 0)

    def test_changed_release_requires_the_reviewed_rule_shapes(self):
        for changed in (
            MODULE_BODY.replace("Dyn(All|Video)", "Dyn(All|Video|New)"),
            MODULE_BODY.replace("grpc.biliapi.net, ", ""),
            MODULE_BODY.replace("script-response-body", "script-request-body", 1),
            MODULE_BODY.replace("response.bundle.js", "different.bundle.js", 1),
            MODULE_BODY.replace("#!version = 0.7.5", "#!version = 0.7.6"),
        ):
            with self.subTest(change=changed), self.assertRaises(ValueError):
                adapt_bilibili(changed, TAG)
        next_module = MODULE_BODY.replace("0.7.5", "0.7.6")
        source, report = adapt_bilibili(next_module, "v0.7.6")
        self.assertEqual(report["release"], "v0.7.6")
        self.assertNotIn(TAG, source)

    def test_only_release_assets_with_verifiable_content_are_accepted(self):
        baseline = sample_release()
        tag, assets = select_release(json.dumps(baseline).encode())
        self.assertEqual(tag, TAG)
        self.assertEqual(set(assets), {MODULE, SCRIPT})
        for name, asset in assets.items():
            verify_asset(asset, name.encode())
            for bad in (b"X" * asset["size"], b""):
                with self.subTest(name=name, data=bad), self.assertRaises(ValueError):
                    verify_asset(asset, bad)
        for changed in (dict(draft=True), dict(prerelease=True), dict(tag_name="latest"),
                        dict(html_url="https://example.invalid/release"),
                        dict(assets=baseline["assets"][:1]),
                        dict(assets=baseline["assets"] * 2)):
            with self.subTest(change=changed), self.assertRaises(ValueError):
                select_release({**baseline, **changed})
        for changed in (dict(size=0), dict(digest=None),
                        dict(browser_download_url=f"{REPO}/releases/latest/download/{SCRIPT}")):
            release = deepcopy(baseline)
            release["assets"][1].update(changed)
            with self.subTest(change=changed), self.assertRaises(ValueError):
                select_release(release)


if __name__ == "__main__":
    unittest.main()
