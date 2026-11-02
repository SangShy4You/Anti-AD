"""Semantic regression tests, using only the Python standard library."""
import importlib.util
import ipaddress
import json
from pathlib import Path
import sys
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "compiler.py"
spec = importlib.util.spec_from_file_location("personal_compiler", MODULE)
compiler = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = compiler
spec.loader.exec_module(compiler)


def source(sid, role="block", policy=None, fmt="mixed", order=1):
    return {"id": sid, "role": role, "original_order": order,
            "expected_policy": policy or ("REJECT" if role == "block" else "DIRECT"),
            "source_format": fmt}


def payload(text):
    if "payload: []" in text:
        return []
    return [json.loads(line.strip()[2:]) for line in text.splitlines() if line.strip().startswith("- ")]


def matches(pattern, host):
    if pattern.startswith("+."):
        return host == pattern[2:] or host.endswith("." + pattern[2:])
    if pattern.startswith("."):
        return host.endswith(pattern)
    return pattern == host


class CompilerTests(unittest.TestCase):
    def compile(self, sources, bodies, personal=None):
        return compiler.compile_profile({"sources": sources}, bodies, personal or {"name": "test"})

    def test_duplicate_suffix_coverage_preserves_exact(self):
        artifacts, report = self.compile([source("a")], {"a": "HOST-SUFFIX,ad.example,REJECT\nHOST,sub.ad.example,REJECT\nHOST-SUFFIX,sub.ad.example,REJECT\nHOST,exact.example,REJECT\nHOST-SUFFIX,ad.example,REJECT"})
        self.assertEqual(payload(artifacts["rules/ads-domain.yaml"]), ["+.ad.example", "exact.example"])
        self.assertFalse(any(matches(p, "other.exact.example") for p in payload(artifacts["rules/ads-domain.yaml"])))
        self.assertEqual(report["ui"]["domain_mode"], "single-file")

    def test_exact_root_allow_leaves_subdomains_blocked(self):
        artifacts, report = self.compile([source("allow", "allow", order=1), source("block", order=2)],
            {"allow": "DOMAIN,log.example,DIRECT", "block": "DOMAIN-SUFFIX,log.example,REJECT"})
        self.assertEqual(payload(artifacts["rules/ads-domain.yaml"]), [".log.example"])
        self.assertFalse(matches(".log.example", "log.example"))
        self.assertTrue(matches(".log.example", "child.log.example"))
        self.assertEqual(len(report["ui"]["root_only_allow_exceptions_encoded_as_leading_dot"]), 1)

    def test_later_allow_does_not_override_early_reject(self):
        artifacts, _ = self.compile([source("block", order=1), source("allow", "allow", order=2)],
            {"block": "DOMAIN-SUFFIX,adjust.example,REJECT", "allow": "DOMAIN,app.adjust.example,DIRECT"})
        self.assertEqual(payload(artifacts["rules/ads-domain.yaml"]), ["+.adjust.example"])

    def test_real_child_hole_requires_ordered_stages(self):
        artifacts, report = self.compile([source("allow", "allow", order=1), source("block", order=2)],
            {"allow": "DOMAIN,keep.parent.example,DIRECT", "block": "DOMAIN-SUFFIX,parent.example,REJECT"})
        self.assertEqual(report["ui"]["domain_mode"], "ordered-stages")
        order = report["ui"]["required_domain_order"]
        self.assertEqual([r["policy"] for r in order], ["DIRECT", "REJECT"])
        self.assertNotEqual(order[0]["path"], "rules/ads-domain.yaml")
        self.assertEqual(order[1]["path"], "rules/ads-domain.yaml")
        self.assertEqual(payload(artifacts[order[0]["path"]]), ["keep.parent.example"])
        self.assertEqual(payload(artifacts[order[1]["path"]]), ["+.parent.example"])

    def test_domainset_dot_includes_root_but_native_dot_does_not(self):
        artifacts, _ = self.compile([source("a", fmt="surge_domainset")], {"a": ".tracker.example\nexact.example"})
        self.assertEqual(set(payload(artifacts["rules/ads-domain.yaml"])), {"+.tracker.example", "exact.example"})
        artifacts, _ = self.compile([source("a", fmt="domain")], {"a": ".tracker.example"})
        self.assertEqual(payload(artifacts["rules/ads-domain.yaml"]), [".tracker.example"])

    def test_keyword_not_smuggled_into_domain_and_keeps_order(self):
        artifacts, report = self.compile([source("early", order=1), source("allow", "allow", order=2), source("late", order=3)],
            {"early": "DOMAIN-KEYWORD,analytics,REJECT", "allow": "DOMAIN,analytics.example,DIRECT", "late": "DOMAIN-SUFFIX,analytics.example,REJECT"})
        self.assertEqual(payload(artifacts["rules/ads-domain.yaml"]), [".analytics.example"])
        advanced = artifacts["rules/advanced-fragment.yaml"]
        self.assertLess(advanced.index("DOMAIN-KEYWORD,analytics"), advanced.index("DOMAIN,analytics.example"))
        self.assertEqual(report["ui"]["cross_type_examples"][0]["source"], "early")

    def test_ip_subtraction_and_early_block(self):
        artifacts, _ = self.compile([source("early", order=1), source("allow", "allow", order=2), source("late", order=3)],
            {"early": "IP-CIDR,10.0.0.1/32,REJECT", "allow": "IP-CIDR,10.0.0.0/30,DIRECT", "late": "IP-CIDR,10.0.0.0/29,REJECT"})
        nets = [ipaddress.ip_network(p) for p in payload(artifacts["rules/ads-ip.yaml"])]
        found = {str(ipaddress.ip_address(i)) for i in range(int(ipaddress.ip_address("10.0.0.0")), int(ipaddress.ip_address("10.0.0.7"))+1) if any(ipaddress.ip_address(i) in net for net in nets)}
        self.assertEqual(found, {"10.0.0.1", "10.0.0.4", "10.0.0.5", "10.0.0.6", "10.0.0.7"})

    def test_manual_allow_wins_manual_reject(self):
        artifacts, report = self.compile([source("upstream")], {"upstream": "DOMAIN-SUFFIX,ad.example,REJECT"},
            {"allow": {"domains": ["ad.example"]}, "reject": {"domains": ["ad.example"]}})
        self.assertEqual(payload(artifacts["rules/ads-domain.yaml"]), [".ad.example"])
        self.assertIn("personal_allow", str(report["ui"]["root_only_allow_exceptions_encoded_as_leading_dot"]))

    def test_missing_body_unknown_type_and_script_fail(self):
        for bodies in ({}, {"a": "MALFORMED-RULE,garbage"}, {"a": "function update() { return 1; }"}, {"a": "{\"payload\": []}"}):
            with self.subTest(bodies=bodies), self.assertRaises(ValueError):
                self.compile([source("a")], bodies)

    def test_known_user_agent_audited_not_exported(self):
        artifacts, report = self.compile([source("a")], {"a": "USER-AGENT,AVOS*,REJECT\nDOMAIN,ad.example,REJECT"})
        self.assertEqual(payload(artifacts["rules/ads-domain.yaml"]), ["ad.example"])
        self.assertEqual(report["issues"][0]["category"], "unsupported-user-agent")
        self.assertFalse(report["issues"][0]["exported"])

    def test_deterministic_and_only_rules_paths(self):
        args = ([source("a")], {"a": "DOMAIN,ad.example,REJECT"})
        first = self.compile(*args)
        self.assertEqual(first, self.compile(*args))
        self.assertTrue(all(p.startswith("rules/") and ".." not in p for p in first[0]))


if __name__ == "__main__":
    unittest.main()
