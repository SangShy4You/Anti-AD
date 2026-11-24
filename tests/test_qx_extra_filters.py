import json
from pathlib import Path
import unittest

from scripts.qx_extra_filters import extract_fmz_ad_filters, REVIEWED_TAIL_PATH, SOURCE_URL


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

    def test_compound_ad_and_metrics_names_are_restored_by_exact_review(self):
        source = ("# > Apple\nhost, metrics.apple.com, reject\n"
                  "host, webproxy-advp.iad-apple.com, reject\n"
                  "# > 叮咚买菜\nhost, trackercollect.ddxq.mobi, reject\n"
                  "# > 建行生活\nhost, o2o-ad-log-gateway.alibaba.com, reject\n"
                  "# > 喜马拉雅\nhost-suffix, adse-v2.ximalaya.com, reject\n"
                  "# > 广告联盟\nhost-suffix, miaozhen.com, reject\n")
        text, report = extract_fmz_ad_filters(source)
        for value in ("metrics.apple.com", "webproxy-advp.iad-apple.com", "trackercollect.ddxq.mobi", "o2o-ad-log-gateway.alibaba.com", "adse-v2.ximalaya.com"):
            self.assertIn(value, text)
        self.assertEqual(report["reviewed_supplements_selected"], 5)

    def test_supplements_keep_keyword_type_and_do_not_widen_to_parent_domain(self):
        text, report = self.compile("# > 酷狗音乐\nhost-keyword, adsfilebssdlbig.ali.kugou.com, reject\nhost, metrics.future-example.com, reject")
        self.assertIn("host-keyword, adsfilebssdlbig.ali.kugou.com, reject", text)
        self.assertNotIn("host-suffix, kugou.com", text)
        self.assertNotIn("metrics.future-example.com", text)
        self.assertEqual(report["reviewed_supplements_selected"], 1)

    def test_review_keeps_business_push_safety_and_unknown_ips_out(self):
        source = ("# > 爱奇艺\nhost, api.iqiyi.com, reject\n"
                  "# > Google\nhost, safebrowsing.googleapis.com, reject\n"
                  "# > Soul\nip-cidr, 47.56.131.76/32, reject\n"
                  "# > 搜狗输入法\nhost-suffix, push-service-ios.sginput.qq.com, reject\n"
                  "# > 广告联盟\nhost-suffix, miaozhen.com, reject\n")
        text, _ = extract_fmz_ad_filters(source)
        for value in ("api.iqiyi.com", "safebrowsing.googleapis.com", "47.56.131.76", "push-service-ios.sginput.qq.com"):
            self.assertNotIn(value, text)

    def test_review_table_accounts_for_every_original_candidate(self):
        review = json.loads(REVIEWED_TAIL_PATH.read_bytes())
        self.assertEqual(len(review["entries"]), 252)
        self.assertEqual(sum(e["decision"] == "include" for e in review["entries"]), 62)
        self.assertTrue(all(e["reason"] and e["source_line_at_review"] for e in review["entries"]))
        for e in review["entries"]:
            if e["decision"] == "include":
                self.assertNotIn(e["normalized_rule"].split(",")[0], {"ip-cidr", "ip6-cidr"})

    def test_malformed_or_broad_review_cannot_override_safety(self):
        for rule in ("host-suffix, google.com, reject", "host, safebrowsing.googleapis.com, reject", "ip-cidr, 203.107.1.0/24, reject", "host, metrics.apple.com, direct"):
            review = {"schema_version": 1, "source_url": SOURCE_URL, "entries": [{"decision": "include", "source_section": "Google", "source_line_at_review": 1, "normalized_rule": rule, "reason": "test"}]}
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                extract_fmz_ad_filters("# > 广告联盟\nhost-suffix, miaozhen.com, reject\n", reviewed_decisions=review)


if __name__ == "__main__":
    unittest.main()
