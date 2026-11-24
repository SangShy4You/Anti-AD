import unittest

from scripts.qx_rewrites import compile_rewrites


class QxRewriteTests(unittest.TestCase):
    def compile(self, text, **selection):
        return compile_rewrites([{"id": "one", "url": "https://example.com/raw", **selection}], {"one": text})

    def test_exact_duplicate_and_provenance(self):
        source = r"^https://ads\.example/x url reject-dict"
        output, audit = compile_rewrites(
            [{"id": "a"}, {"id": "b"}], {"a": source, "b": "  " + source + "  \n"})
        self.assertEqual(output.count(source), 1)
        self.assertEqual(len(audit["rules"][0]["origins"]), 2)
        self.assertEqual(audit["counts"]["exact_duplicates_removed"], 1)

    def test_distinct_response_semantics_remain_in_source_order(self):
        matcher = r"^https://example\.com/a"
        output, audit = self.compile(f"{matcher} url reject-dict\n{matcher} url reject\n")
        self.assertIn("url reject-dict\n", output)
        self.assertIn("url reject\n", output)
        self.assertLess(output.index("url reject-dict\n"), output.index("url reject\n"))
        self.assertEqual(audit["conflicts"][0]["resolution"], "retained-in-source-order")
        self.assertEqual(audit["conflicts"][0]["additional"]["action"], "reject")
        self.assertEqual(audit["counts"]["conflicts_excluded"], 0)

    def test_kuaishou_independent_cleanup_is_not_a_duplicate(self):
        matcher = r"^https:\/\/(apissl|az2-api(-js|-idc)?)\.(gifshow|ksapisrv)\.com\/rest\/system\/startup\?"
        first = f"{matcher} url jsonjq-response-body 'del(.reskinConfig.sidebarExSquareStyle.moreList, .reskinConfig.sidebarExSquareStyle.topList)'"
        second = f"{matcher} url jsonjq-response-body '.sidebarExSquareStyle.commonlyUsedList |= map(select(.title == \"设置\" or .title == \"历史记录\"))'"
        output, audit = compile_rewrites(
            [{"id": "fmz"}, {"id": "later"}],
            {"fmz": first + "\n" + second, "later": second},
        )
        self.assertIn(first, output)
        self.assertIn(second, output)
        self.assertLess(output.index(first), output.index(second))
        self.assertEqual(output.count(second), 1)
        self.assertEqual(audit["counts"]["exact_duplicates_removed"], 1)
        self.assertEqual(audit["counts"]["non_equivalent_overlaps_retained"], 1)

    def test_same_matcher_different_response_scripts_are_both_preserved(self):
        output, audit = self.compile(
            "^https://example.com/a url script-response-body https://example.com/ads.js\n"
            "^https://example.com/a url script-response-body https://example.com/background.js\n"
        )
        self.assertIn("ads.js", output)
        self.assertIn("background.js", output)
        self.assertEqual(len(audit["script_urls"]), 2)

    def test_original_psbc_surge_marker_is_converted_without_losing_ad_rule(self):
        matcher = r"^https?:\/\/static.psbc.com:8090\/mbank_f\/images\/[0-9]+\.png"
        original = matcher + " - reject-200"
        with self.assertRaisesRegex(ValueError, "requires explicit source approval"):
            self.compile(original)
        output, audit = self.compile(original, allow_surge_rewrite_marker=True)
        self.assertIn(matcher + " url reject-200\n", output)
        self.assertEqual(audit["syntax_conversions"][0]["text"], original)
        self.assertEqual(audit["sources"][0]["surge_marker_rules_converted"], 1)

    def test_request_and_response_stages_survive(self):
        output, audit = self.compile(
            "^https://example.com/a url script-request-body https://example.com/a.js\n"
            "^https://example.com/a url script-response-body https://example.com/b.js\n")
        self.assertIn("script-request-body", output)
        self.assertIn("script-response-body", output)
        self.assertEqual(len(audit["cross_stage_matches"]), 1)

    def test_script_query_fragment_and_case_preserved(self):
        url = "https://raw.githubusercontent.com/Owner/Repo/main/Case.js?version=AbC#out=Hant&x=1"
        output, audit = self.compile(f"^https://example.com/a url script-response-body {url}")
        self.assertIn(url, output)
        self.assertEqual(audit["script_urls"], [url])

    def test_url_and_header_left_side_with_spaces(self):
        rule = r"^https://example\.com/a \r\nUser-Agent: Example Agent url-and-header reject-dict"
        output, audit = self.compile(rule)
        self.assertIn(rule, output)
        self.assertEqual(audit["rules"][0]["marker"], "url-and-header")
        self.assertIn("Example Agent", audit["rules"][0]["matcher"])

    def test_url_and_header_missing_header_fails(self):
        with self.assertRaisesRegex(ValueError, "requires URL and header"):
            self.compile("^https://example.com/a url-and-header reject-dict")

    def test_header_replacement_argument_spaces_and_hash(self):
        rule = r"^https://example.com/a url request-header (\r\n)X:.+(\r\n) request-header $1X: Hello #fragment world$2"
        output, _ = self.compile(rule)
        self.assertIn(rule, output)

    def test_comments_bom_crlf_and_leading_note(self):
        output, audit = self.compile(
            "\ufeff# comment\r\n;^https://off url reject\r\n// another comment\r\n"
            "{# visible note #} ^https://on url reject-dict\r\n")
        self.assertNotIn("https://off", output)
        self.assertIn("^https://on url reject-dict", output)
        self.assertEqual(audit["rules"][0]["origins"][0]["line"], 4)

    def test_mixed_filter_collected_not_exported(self):
        output, audit = self.compile("host, allow.example, direct\n^https://ads.example url reject\n")
        self.assertNotIn("host, allow", output)
        self.assertEqual(audit["filter_lines"][0]["rule"], "host, allow.example, direct")
        self.assertFalse(audit["filter_lines"][0]["exported"])

    def test_hostname_stable_exact_dedup_and_exclusion(self):
        output, audit = self.compile(
            "hostname = API.Example.com, api.example.com, -*.example.com, %APPEND%\n"
            "^https://api.example.com/a url reject-dict\n")
        self.assertIn("hostname = api.example.com, -*.example.com\n", output)
        self.assertNotIn("%APPEND%", output)
        self.assertEqual(audit["hostname_conflicts"][0]["inclusion"], "api.example.com")

    def test_remote_resource_is_flat_without_main_profile_headers(self):
        output, _ = self.compile("[rewrite_local]\n^https://api.example/a url reject-dict\n"
                                 "[mitm]\nhostname = api.example\n")
        self.assertIn("^https://api.example/a url reject-dict\n", output)
        self.assertIn("hostname = api.example\n", output)
        self.assertNotIn("[rewrite_local]", output)
        self.assertNotIn("[mitm]", output)

    def test_hostname_selected_subset(self):
        output, _ = self.compile("hostname = a.example, b.example\n^https://a.example url reject\n",
                                 include_hostnames=["a.example"])
        self.assertIn("hostname = a.example\n", output)
        self.assertNotIn("b.example", output)

    def test_allowlist_exclusion_and_staleness(self):
        keep = "^https://good.example url reject"
        remove = "^https://optional.example url reject-dict"
        output, audit = self.compile(keep + "\n" + remove, include_rules=[keep])
        self.assertIn(keep, output)
        self.assertNotIn(remove, output)
        self.assertEqual(audit["exclusions"][0]["kind"], "not-allowlisted")
        output, audit = self.compile(keep + "\n" + remove,
                                     exclude_rules=[{"rule": remove, "reason": "reviewed optional"}])
        self.assertNotIn(remove, output)
        self.assertEqual(audit["exclusions"][0]["reason"], "reviewed optional")
        with self.assertRaisesRegex(ValueError, "stale include_rules"):
            self.compile(keep, include_rules=[remove])
        with self.assertRaisesRegex(ValueError, "requires a reason"):
            self.compile(keep, exclude_rules={keep: ""})

    def test_explicit_unsupported_line_exclusion(self):
        text = "legacy-setting = true\n^https://ads.example url reject"
        with self.assertRaisesRegex(ValueError, "unsupported active"):
            self.compile(text)
        _, audit = self.compile(text, excluded_lines={"legacy-setting = true": "not part of native rewrites"})
        self.assertEqual(audit["exclusions"][0]["kind"], "explicit-line")

    def test_certificate_must_not_pass_through(self):
        with self.assertRaisesRegex(ValueError, "unsupported active"):
            self.compile("[mitm]\np12 = SECRET\n[rewrite_local]\n^https://x url reject")

    def test_empty_html_unknown_action_and_missing_argument_fail(self):
        for text in ["", "<!doctype html><html>Error</html>", "^https://x url unknown", "^https://x url script-response-body", "^https://x url reject unexpected"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.compile(text)

    def test_invalid_or_empty_selection_fails(self):
        with self.assertRaisesRegex(ValueError, "no rewrite rules"):
            self.compile("^https://x url reject", include_rules=[])
        with self.assertRaisesRegex(ValueError, "stale include_hostnames"):
            self.compile("^https://x url reject", include_hostnames=["absent.example"])

    def test_duplicate_source_and_unsupported_section_fail(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            compile_rewrites([{"id": "one"}, {"id": "one"}], {"one": "^https://x url reject"})
        with self.assertRaisesRegex(ValueError, "unsupported section"):
            self.compile("[Script]\n^https://x url reject")

    def test_local_dependencies_are_reported(self):
        _, audit = self.compile("^https://x/a url script-response-body local.js\n"
                                "^https://x/b url echo-response text/html echo-response index.html\n")
        self.assertEqual(audit["local_script_references"][0]["reference"], "local.js")
        self.assertEqual(len(audit["local_data_references"]), 1)
        self.assertEqual(audit["script_urls"], [])

    def test_output_deterministic_across_newline_changes(self):
        text = "hostname = ads.example\n^https://ads.example url reject-dict\n"
        a, _ = self.compile(text)
        b, _ = self.compile(text.replace("\n", "\r\n"))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
