from copy import deepcopy
import unittest

from scripts.qx_profile_dedup import deduplicate_profile
from scripts.qx_rewrites import compile_rewrites


class ProfileDedupTests(unittest.TestCase):
    def prepare(self, body_a, body_b, *, body_c=None):
        products, reports = {}, {}
        for name, body in (("ads.conf", body_a), ("miniapps.conf", body_b), ("web.conf", body_c)):
            if body is None:
                continue
            text, report = compile_rewrites([{"id": name, "url": "https://example.invalid/" + name}], {name: body})
            products["rules/quantumultx/" + name] = text.encode("utf-8")
            reports[name] = report
        return products, reports

    def test_only_exact_later_rule_removed_and_hostnames_headers_preserved(self):
        repeated = r"^https://api\.example/ads url reject-dict"
        products, reports = self.prepare(repeated + "\nhostname = api.example",
                                         repeated + "\n^https://mini.example/banner url reject\nhostname = mini.example,-skip.example")
        path = "rules/quantumultx/miniapps.conf"
        before = products[path]
        products[path] = before.replace(b"hostname = ", b"# Header kept intact\r\nhostname = reviewed.example, ")
        reports["miniapps.conf"]["reviewed_hostname_additions"] = {"reviewed.example": "fixture"}
        original_inputs = [s["input_rules"] for s in reports["miniapps.conf"]["sources"]]
        summary = deduplicate_profile(products, reports, ["ads.conf", "miniapps.conf"])
        self.assertNotIn(repeated.encode(), products[path])
        self.assertIn(b"# Header kept intact\r\nhostname = reviewed.example, mini.example, -skip.example", products[path])
        self.assertEqual(summary[1]["duplicates_removed"], 1)
        self.assertEqual(summary[1]["requires_earlier_products"], ["ads.conf"])
        self.assertEqual(reports["miniapps.conf"]["counts"]["rules"], 1)
        self.assertEqual(reports["miniapps.conf"]["actions"], {"reject": 1})
        self.assertEqual(reports["miniapps.conf"]["reviewed_hostname_additions"], {"reviewed.example": "fixture"})
        self.assertEqual([s["input_rules"] for s in reports["miniapps.conf"]["sources"]], original_inputs)
        self.assertEqual(reports["miniapps.conf"]["sources"][0]["exported_rules_before_profile_dedup"], 2)
        self.assertEqual(reports["miniapps.conf"]["sources"][0]["exported_rules"], 1)
        self.assertEqual(summary[1]["examples"][0]["removed_origins"][0]["source"], "miniapps.conf")

    def test_different_actions_patterns_and_header_conditions_are_not_deduplicated(self):
        products, reports = self.prepare(
            "^https://example/ads url reject\n^https://example/a ^POST url-and-header reject-dict",
            "^https://example/ads url reject-dict\n^https://example/a ^GET url-and-header reject-dict\n^https://example/ads/ url reject")
        original = deepcopy(products)
        summary = deduplicate_profile(products, reports, ["ads.conf", "miniapps.conf"])
        self.assertEqual(products, original)
        self.assertEqual([s["duplicates_removed"] for s in summary], [0, 0])

    def test_script_metadata_only_tracks_remaining_rules_preserving_full_parameters(self):
        shared = "https://raw.githubusercontent.com/o/r/main/a.js?q=1#one"
        unique = "https://raw.githubusercontent.com/o/r/main/a.js?q=1#two"
        repeated = "^https://example/a url script-response-body " + shared
        products, reports = self.prepare(repeated,
            repeated + "\n^https://example/b url script-response-body " + unique)
        deduplicate_profile(products, reports, ["ads.conf", "miniapps.conf"])
        later = reports["miniapps.conf"]
        self.assertEqual(later["script_urls"], [unique])
        self.assertEqual(later["counts"]["script_urls"], 1)
        self.assertEqual([r["reference"] for r in later["script_references"]], [unique])
        self.assertTrue(all(r["rule"] != repeated for r in later["script_references"]))
        self.assertIn(unique.encode(), products["rules/quantumultx/miniapps.conf"])

    def test_shared_script_url_stays_when_another_remaining_pattern_uses_it(self):
        url = "https://raw.githubusercontent.com/o/r/main/a.js#argument"
        repeated = "^https://example/a url script-response-body " + url
        products, reports = self.prepare(repeated,
            repeated + "\n^https://example/b url script-response-body " + url)
        deduplicate_profile(products, reports, ["ads.conf", "miniapps.conf"])
        self.assertEqual(reports["miniapps.conf"]["script_urls"], [url])
        self.assertEqual(len(reports["miniapps.conf"]["script_references"]), 1)

    def test_full_profile_order_is_authoritative_and_other_products_untouched(self):
        repeated = "^https://example/a url reject"
        products, reports = self.prepare(repeated + "\n^https://example/a-only url reject",
                                         repeated + "\n^https://example/b-only url reject",
                                         body_c=repeated + "\n^https://example/c-only url reject")
        outside = products["rules/quantumultx/web.conf"]
        outside_report = deepcopy(reports["web.conf"])
        summary = deduplicate_profile(products, reports, ["miniapps.conf", "ads.conf"])
        self.assertIn(repeated.encode(), products["rules/quantumultx/miniapps.conf"])
        self.assertNotIn(repeated.encode(), products["rules/quantumultx/ads.conf"])
        self.assertEqual(summary[1]["examples"][0]["kept_product"], "miniapps.conf")
        self.assertEqual(products["rules/quantumultx/web.conf"], outside)
        self.assertEqual(reports["web.conf"], outside_report)

    def test_empty_later_resource_or_bad_order_leaves_all_inputs_unchanged(self):
        repeated = "^https://example/a url reject"
        products, reports = self.prepare(repeated, repeated)
        before_products, before_reports = deepcopy(products), deepcopy(reports)
        for order in (["ads.conf", "miniapps.conf"], ["ads.conf", "ads.conf"], ["ads.conf", "unknown.conf"], ["../ads.conf"]):
            with self.subTest(order=order), self.assertRaises(ValueError):
                deduplicate_profile(products, reports, order)
            self.assertEqual(products, before_products)
            self.assertEqual(reports, before_reports)

    def test_pinned_output_or_report_drift_stops_before_any_mutation(self):
        url = "https://raw.githubusercontent.com/o/r/main/a.js"
        repeated = "^https://example/a url script-response-body " + url
        products, reports = self.prepare(repeated + "\n^https://example/a-only url reject",
                                         repeated + "\n^https://example/b-only url reject")
        products["rules/quantumultx/miniapps.conf"] = products["rules/quantumultx/miniapps.conf"].replace(b"/main/", b"/" + b"1" * 40 + b"/")
        before_products, before_reports = deepcopy(products), deepcopy(reports)
        with self.assertRaisesRegex(ValueError, "pre-pin native product"):
            deduplicate_profile(products, reports, ["ads.conf", "miniapps.conf"])
        self.assertEqual(products, before_products)
        self.assertEqual(reports, before_reports)

    def test_profile_examples_are_capped_without_losing_full_count(self):
        common = [f"^https://example/{i} url reject" for i in range(120)]
        products, reports = self.prepare("\n".join(common), "\n".join(common + ["^https://mini/unique url reject"]))
        summary = deduplicate_profile(products, reports, ["ads.conf", "miniapps.conf"])
        self.assertEqual(summary[1]["duplicates_removed"], 120)
        self.assertEqual(len(summary[1]["examples"]), 100)
        self.assertEqual(summary[1]["rules_after"], 1)
        self.assertEqual(summary[1]["removed_source_counts"], {"miniapps.conf": 120})


if __name__ == "__main__":
    unittest.main()
