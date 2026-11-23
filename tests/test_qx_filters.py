"""Regression tests for QX policy ordering and native filter semantics."""
import importlib.util
from pathlib import Path
import sys
import unittest


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "qx_filters.py"
spec = importlib.util.spec_from_file_location("qx_filters", MODULE)
qx = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = qx
spec.loader.exec_module(qx)


def source(sid, policy="reject", fmt="mixed", **extra):
    return {"id": sid, "name": sid, "expected_policy": policy,
            "source_format": fmt, **extra}


def rows(text):
    return [x for x in text.splitlines() if x and not x.startswith("#")]


class QXFiltersTests(unittest.TestCase):
    def test_aliases_dedup_and_policy_conflicts_keep_original_priority(self):
        text, report = qx.compile_filters(
            [source("early"), source("late", "direct")],
            {"early": "DOMAIN,AD.Example,REJECT\nHOST,ad.example,reject",
             "late": "HOST,ad.example,DIRECT\nHOST,keep.example,DIRECT"})
        self.assertEqual(rows(text), ["host, ad.example, reject", "host, keep.example, direct"])
        self.assertEqual(report["duplicate_rules_removed"], 2)
        self.assertEqual(report["conflict_rules_removed_first_match_wins"], 1)
        self.assertEqual(report["conflicts"][0]["kept_source"], "early")

    def test_parent_child_and_intervening_policy_are_not_compacted(self):
        text, report = qx.compile_filters(
            [source("allow", "direct"), source("deny"), source("later", "direct")],
            {"allow": "HOST,keep.example.com,DIRECT",
             "deny": "DOMAIN-SUFFIX,example.com,REJECT",
             "later": "DOMAIN,other.example.com,DIRECT"})
        self.assertEqual(rows(text), ["host, keep.example.com, direct",
                                     "host-suffix, example.com, reject",
                                     "host, other.example.com, direct"])
        self.assertFalse(report["domain_parent_child_compaction"])

    def test_all_user_agents_kept_and_not_url_decoded_or_lowercased(self):
        agents = ["AVOS*", "%E8%BF%85%E9%9B%B7", "MicroMessenger*", "WeChat*"]
        text, report = qx.compile_filters([source("ua", "全球加速")],
            {"ua": "\n".join(f"USER-AGENT,{a},original" for a in agents)})
        self.assertEqual(rows(text), [f"user-agent, {a}, 全球加速" for a in agents])
        self.assertEqual(report["type_counts"]["user-agent"], 4)

    def test_ip_normalization_and_options_preserved_with_distinct_qualifiers(self):
        body = "\n".join([
            "IP-CIDR,192.0.2.129/24,old,no-resolve,extended-matching",
            "IP-CIDR,192.0.2.0/24,old,no-resolve,extended-matching",
            "IP-CIDR,192.0.2.0/24,old",
            "IP-CIDR6,2001:db8:0:0::1/64,old,no-resolve",
            "IP-ASN,00132203,old,force-remote-dns",
            "HOST,example.com,old,force-cellular,via-interface=pdp_ip0",
        ])
        text, report = qx.compile_filters([source("ip", "direct")], {"ip": body})
        self.assertEqual(report["output_rules"], 5)
        self.assertIn("ip-cidr, 192.0.2.0/24, direct, no-resolve, extended-matching", rows(text))
        self.assertIn("ip-cidr, 192.0.2.0/24, direct", rows(text))
        self.assertIn("ip6-cidr, 2001:db8::/64, direct, no-resolve", rows(text))
        self.assertIn("ip-asn, 132203, direct, force-remote-dns", rows(text))
        self.assertIn("host, example.com, direct, force-cellular, via-interface=pdp_ip0", rows(text))

    def test_original_row_policies_retained_if_force_policy_is_explicitly_null(self):
        text, _ = qx.compile_filters([source("mixed", force_policy=None)],
            {"mixed": "HOST,ad.example,reject-dict\nHOST,keep.example,DIRECT"})
        self.assertEqual(rows(text), ["host, ad.example, reject-dict", "host, keep.example, direct"])

    def test_force_policy_supports_two_field_or_option_as_third_field(self):
        text, _ = qx.compile_filters([source("short")],
            {"short": "DOMAIN,ad.example\nIP-CIDR,192.0.2.1/32,no-resolve"})
        self.assertEqual(rows(text), ["host, ad.example, reject",
                                     "ip-cidr, 192.0.2.1/32, reject, no-resolve"])

    def test_domainset_dot_and_plain_domain_mean_different_matches(self):
        text, _ = qx.compile_filters([source("ds", fmt="surge_domainset")],
                                    {"ds": ".ads.example\nexact.example"})
        self.assertEqual(rows(text), ["host-suffix, ads.example, reject", "host, exact.example, reject"])
        text, _ = qx.compile_filters([source("native", fmt="domain_text")],
                                    {"native": "+.parent.example\n.children.example\nroot.example"})
        self.assertEqual(rows(text), ["host-suffix, parent.example, reject",
                                     "host-wildcard, *.children.example, reject",
                                     "host, root.example, reject"])

    def test_overrides_are_explicit_and_precede_upstream_rules(self):
        text, report = qx.compile_filters([source("block")],
            {"block": "HOST,keep.example,REJECT\nHOST-SUFFIX,example,REJECT"},
            ["HOST,keep.example,DIRECT"])
        self.assertEqual(rows(text)[0], "host, keep.example, direct")
        self.assertEqual(report["conflicts"][0]["kept_source"], "personal_overrides")

    def test_trailing_dot_is_preserved_and_reported_without_silent_broadening(self):
        text, report = qx.compile_filters([source("legacy")],
                                        {"legacy": "HOST-SUFFIX,abbp1.space.,REJECT"})
        self.assertEqual(rows(text), ["host-suffix, abbp1.space., reject"])
        self.assertEqual(report["issues"][0]["kind"], "trailing-dot-preserved")

    def test_unknown_options_types_and_missing_inputs_fail_instead_of_dropping(self):
        for body in ["PROCESS-NAME,foo.exe,REJECT", "HOST,a.example,reject,unknown-option",
                     "HOST,a.example,reject,via-interface=", "payload:", "function run() {}",
                     "IP-CIDR,2001:db8::/32,REJECT", "IP-ASN,not-a-number,REJECT"]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                qx.compile_filters([source("bad")], {"bad": body})
        with self.assertRaises(ValueError):
            qx.compile_filters([source("missing")], {})

    def test_bounded_samples_keep_full_counts(self):
        body = "\n".join(f"HOST,{n}.example,reject" for n in range(110))
        text, report = qx.compile_filters([source("a"), source("b", "direct")],
                                        {"a": body, "b": body})
        self.assertEqual(report["conflict_rules_removed_first_match_wins"], 110)
        self.assertEqual(len(report["conflicts"]), 100)
        self.assertEqual(len(rows(text)), 110)

    def test_disabled_sources_need_no_body_and_repeated_ids_fail(self):
        text, report = qx.compile_filters([source("off", enabled=False), source("on")],
                                        {"on": "HOST,a.example,reject"})
        self.assertEqual(report["disabled_sources"], ["off"])
        with self.assertRaises(ValueError):
            qx.compile_filters([source("a"), source("a")], {"a": "HOST,a.example,reject"})

    def test_explicit_scope_exclusion_records_reason_and_upstream_removal_is_not_fatal(self):
        text, report = qx.compile_filters([source("a", exclude_rules={
            "HOST,license.example,reject": "Licensing is outside adblock scope",
            "HOST,removed.example,reject": "Removed upstream"})],
            {"a": "HOST,license.example,reject\nHOST,ads.example,reject"})
        self.assertEqual(rows(text), ["host, ads.example, reject"])
        self.assertEqual(report["sources"][0]["excluded_rules"], 1)
        self.assertEqual({x["kind"] for x in report["issues"]},
                         {"explicit-exclusion", "exclusion-not-present"})


if __name__ == "__main__":
    unittest.main()
