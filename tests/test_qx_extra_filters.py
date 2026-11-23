import unittest

from scripts.qx_extra_filters import extract_fmz_ad_filters


class ExtraFilterTests(unittest.TestCase):
    def compile(self, text):
        return extract_fmz_ad_filters(text + "\n# > 广告联盟\nhost-suffix, miaozhen.com, reject\n")

    def test_ad_and_tracking_labels_in_known_app_sections(self):
        text, report = self.compile("# > 12123\nhost, ads.example.com, reject\nhost-suffix, analytics.example.com, reject\nhost-suffix, api.example.com, reject")
        self.assertIn("host, ads.example.com, reject", text)
        self.assertIn("host-suffix, analytics.example.com, reject", text)
        self.assertNotIn("host-suffix, api.example.com, reject", text)
        self.assertEqual(report["input_filter_rows"], 4)
        self.assertEqual(report["selected_filter_rows"], 3)

    def test_license_security_update_and_whole_site_are_not_selected(self):
        text, report = self.compile("# > 12123\nhost-suffix, activate.adobe.com, reject\nhost, safebrowsing.googleapis.com, reject\nhost-suffix, ad.update.example.com, reject\nhost-suffix, temu.com, reject\nhost-suffix, rumble.com, reject")
        for forbidden in ("activate.adobe.com", "safebrowsing.googleapis.com", "ad.update.example.com", "temu.com", "rumble.com"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(report["not_selected_filter_rows"], 5)

    def test_unknown_app_heading_is_reported_even_for_ad_host(self):
        text, report = self.compile("# > Unreviewed Future Application\nhost-suffix, ad.example.com, reject")
        self.assertNotIn("ad.example.com", text)
        self.assertEqual(report["unknown_app_sections"], ["Unreviewed Future Application"])

    def test_unknown_vendor_heading_is_not_wholesale_trusted(self):
        text, report = extract_fmz_ad_filters("# > 广告联盟\nhost-suffix, miaozhen.com, reject\n# Future Ad Supplier\nhost-suffix, future-company.com, reject\n")
        self.assertNotIn("future-company.com", text)
        self.assertEqual(report["unknown_network_vendors"], ["Future Ad Supplier"])

    def test_reviewed_ad_vendor_but_not_push_cdn_business_or_safety(self):
        text, report = extract_fmz_ad_filters("# > 广告联盟\nhost-suffix, getui.com, reject\nhost-suffix, cdntips.net, reject\n# Ad-Stir\nhost-suffix, ad-stir.com, reject\nhost-suffix, google.com, reject\nhost, safebrowsing.googleapis.com, reject\n")
        self.assertIn("ad-stir.com", text)
        self.assertNotIn("getui.com", text)
        self.assertNotIn("cdntips.net", text)
        self.assertNotIn("google.com", text)
        self.assertNotIn("safebrowsing.googleapis.com", text)

    def test_ota_and_captcha_vendors_are_explicitly_excluded(self):
        text, report = extract_fmz_ad_filters("# > 广告联盟\nhost-suffix, miaozhen.com, reject\n# Adups\nhost-suffix, adups.com, reject\n# Touclick\nhost-suffix, cap.touclick.com, reject\n")
        self.assertNotIn("adups.com", text)
        self.assertNotIn("cap.touclick.com", text)
        self.assertEqual(report["not_selected_filter_rows"], 2)

    def test_only_reviewed_tieba_ip_is_kept(self):
        text, _ = self.compile("# > 百度贴吧\nIP-CIDR, 180.76.76.200/32, REJECT, no-resolve\nIP-CIDR, 203.107.1.1/24, REJECT\nIP6-CIDR, 2402:db40:5100:1011::5/128, REJECT")
        self.assertIn("ip-cidr, 180.76.76.200/32, reject, no-resolve", text)
        self.assertNotIn("203.107.1.0/24", text)
        self.assertNotIn("2402:db40", text)

    def test_nonreject_policy_and_broad_keyword_are_not_overridden(self):
        text, report = self.compile("# > 12123\nhost, ad.example.com, direct\nhost-keyword, analytics, reject\nUSER-AGENT, AVOS*, reject")
        self.assertNotIn("ad.example.com", text)
        self.assertNotIn("analytics", text)
        self.assertNotIn("AVOS", text)
        self.assertEqual(report["not_selected_filter_rows"], 3)

    def test_rewrites_and_comments_are_not_treated_as_filters(self):
        text, report = self.compile("# > 12123\n#host-suffix, ads.disabled.example.com, reject\n^https://api.example.com/ads url reject\nhostname = api.example.com")
        self.assertEqual(report["input_filter_rows"], 1)
        self.assertNotIn("api.example.com", text)

    def test_unsupported_qualifier_stops_instead_of_silent_loss(self):
        with self.assertRaises(ValueError):
            self.compile("# > 12123\nhost, ad.example.com, reject, made-up-option")

    def test_missing_marker_empty_html_and_empty_selection_stop(self):
        for source in ("", "<html>Blocked</html>", "# > 12123\nhost, ad.example.com, reject", "# > 广告联盟\nhost-suffix, rumble.com, reject"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                extract_fmz_ad_filters(source)

    def test_idempotent_classification(self):
        source = "# > 12123\nhost, ads.example.com, reject\n# > 广告联盟\nhost-suffix, miaozhen.com, reject"
        self.assertEqual(extract_fmz_ad_filters(source), extract_fmz_ad_filters(source))


if __name__ == "__main__":
    unittest.main()
