import json
import unittest

from scripts.qx_mixed_guard import validate_mixed_reference


class MixedGuardTests(unittest.TestCase):
    def test_out_retains_other_rules_without_exposing_bodies(self):
        body = "^https://example.com/ad_impression url reject-200\n^https://example.com/account url script-response-body https://raw.githubusercontent.com/o/r/main/account.js\nhostname = example.com\n"
        report = validate_mixed_reference(body, {"mode": "out", "keys": ["ad_impression"], "expected_selected": 1, "title": "split"})
        self.assertEqual(report["input_rule_count"], 2)
        self.assertEqual(report["selected_rule_count"], 1)
        self.assertEqual(report["retained_rule_count"], 1)
        self.assertEqual(report["filtered_rule_count"], 1)
        self.assertFalse(report["rule_bodies_exported"])
        self.assertNotIn("https://example.com", json.dumps(report))
        self.assertNotIn("account.js", json.dumps(report))

    def test_in_keeps_selected_union_with_case_insensitive_keys(self):
        body = "a url script-response-body https://raw.githubusercontent.com/o/r/main/Foo.js\nb url script-response-body https://raw.githubusercontent.com/o/r/main/Bar.js\nc url reject\n"
        report = validate_mixed_reference(body, {"mode": "in", "keys": ["foo.JS", "BAR.js"], "expected_selected": 2})
        self.assertEqual(report["selected_rule_count"], 2)
        self.assertEqual(report["retained_rule_count"], 2)
        self.assertEqual(report["filtered_rule_count"], 1)

    def test_comments_disabled_rules_and_hostname_are_not_counted(self):
        body = "# ad url reject\n; ad url reject\n// ad url reject\nx -url reject\ny - reject\nhostname = ad\nactive url reject\n"
        report = validate_mixed_reference(body, {"mode": "in", "keys": ["active"]})
        self.assertEqual(report["input_rule_count"], 1)
        self.assertEqual(report["selected_rule_evidence"][0]["line"], 7)

    def test_url_and_header_and_note_annotation_are_counted(self):
        body = "{# public note #} ^https://example.com/ ^POST url-and-header reject\n"
        report = validate_mixed_reference(body, {"mode": "in", "keys": ["^post"]})
        self.assertEqual(report["input_rule_count"], 1)

    def test_literal_regex_characters_are_not_regex_patterns(self):
        body = r"^https://example.com/(entry|friend) url reject" + "\n^https://example.com/entry url reject\n"
        report = validate_mixed_reference(body, {"mode": "out", "keys": ["(entry|friend)"]})
        self.assertEqual(report["retained_rule_count"], 1)

    def test_zero_matches_or_multiple_matches_stop(self):
        for body in ("a url reject\n", "ad url reject\nad_second url reject\n"):
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, "each key"):
                validate_mixed_reference(body, {"mode": "out", "keys": ["ad"]})

    def test_total_union_count_must_match_reviewed_count(self):
        body = "ad_one url reject\n"
        with self.assertRaisesRegex(ValueError, "distinct selected"):
            validate_mixed_reference(body, {"mode": "out", "keys": ["ad", "one"], "expected_selected": 2})

    def test_unselected_rule_changes_are_allowed(self):
        spec = {"mode": "out", "keys": ["selected"], "expected_selected": 1}
        first = validate_mixed_reference("selected url reject\nold url reject\n", spec)
        second = validate_mixed_reference("selected url reject\nnew url reject\nanother url reject\n", spec)
        self.assertEqual(first["selected_rule_count"], second["selected_rule_count"])
        self.assertEqual(second["retained_rule_count"], 2)
        self.assertNotEqual(first["source_sha256"], second["source_sha256"])

    def test_invalid_specs_do_not_silently_widen_selection(self):
        for spec in ({}, {"mode": "all", "keys": ["a"]}, {"mode": "in", "keys": []},
                     {"mode": "in", "keys": [""]}, {"mode": "in", "keys": ["a", "A"]},
                     {"mode": "in", "keys": ["a"], "expected_selected": True},
                     {"mode": "in", "keys": ["a"], "expected_selected": 0},
                     {"mode": "in", "keys": ["a"], "title": ""}):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_mixed_reference("a url reject", spec)

    def test_empty_html_and_missing_active_rewrites_stop(self):
        spec = {"mode": "out", "keys": ["a"]}
        for body in ("", "<!DOCTYPE html><html>error</html>", "\ufeff<html>error</html>", "hostname = a\n"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                validate_mixed_reference(body, spec)

    def test_hash_and_report_are_deterministic(self):
        body = "\ufeffa url reject\n"
        spec = {"mode": "in", "keys": ["a"]}
        self.assertEqual(validate_mixed_reference(body, spec), validate_mixed_reference(body, spec))


if __name__ == "__main__":
    unittest.main()
