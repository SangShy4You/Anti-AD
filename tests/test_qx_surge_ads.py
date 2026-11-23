import re
import unittest

from scripts import qx_surge_ads as adapter
from scripts.qx_rewrites import compile_rewrites


def advertising(extra=""):
    return ("#!name=Advertising\n[Rule]\n[URL Rewrite]\n"
            r"(?i)\b\/ad\/ - reject" + "\n" + r"^https:\/\/api\.example\.com\/Ads - reject" +
            "\n" + extra + "[MITM]\nhostname = %APPEND% api.example.com,*.example.com\n")


def youtube():
    return ("[Rule]\n" + adapter.YOUTUBE_UDP_RULE + "\n[URL Rewrite]\n"
            + adapter.YOUTUBE_HEADER_PATTERN + " $1$2$3 header\n"
            + r"^https?:\/\/s\.youtube\.com\/api\/stats\/ads - reject" + "\n[Script]\n"
            + "youtube-proto = type=http-response,pattern=" + adapter.YOUTUBE_SCRIPT_PATTERN
            + ",requires-body=1,binary-body-mode=1,max-size=2097152,script-path=" + adapter.YOUTUBE_SCRIPT
            + "\n[MITM]\nhostname = %APPEND% -redirector*.googlevideo.com,*.googlevideo.com,youtubei.googleapis.com\n")


class SurgeAdTests(unittest.TestCase):
    def test_advertising_preserves_case_and_regex_and_outputs_flat_native(self):
        native, report = adapter.adapt_surge_ad_source({"id": "ad", "surge_ad_kind": "advertising"}, advertising())
        self.assertIn(r"(?i)\b\/ad\/ url reject", native)
        self.assertIn(r"api\.example\.com\/Ads url reject", native)
        self.assertNotIn("[rewrite_local]", native)
        self.assertNotIn("%APPEND%", native)
        self.assertEqual(report["counts"]["reject_rules"], 2)
        combined, parsed = compile_rewrites([{"id": "ad"}], {"ad": native})
        self.assertEqual(parsed["counts"]["rules"], 2)

    def test_youtube_binary_hook_native_support_and_explicit_udp_carry(self):
        native, report = adapter.adapt_surge_ad_source({"id": "yt", "surge_ad_kind": "youtube"}, youtube())
        self.assertIn("url script-response-body " + adapter.YOUTUBE_SCRIPT, native)
        self.assertNotIn("AND,", native)
        self.assertNotIn("udp_drop_list", native)
        self.assertIn("-redirector*.googlevideo.com", native)
        self.assertEqual(report["explicit_carry"][0]["rule"], adapter.YOUTUBE_UDP_RULE)
        self.assertEqual(report["counts"]["output_rewrite_rules"], 3)
        _, parsed = compile_rewrites([{"id": "yt"}], {"yt": native})
        self.assertEqual(parsed["script_urls"], [adapter.YOUTUBE_SCRIPT])

    def test_author_native_mode_keeps_exactly_one_external_hook_requirement(self):
        native, report = adapter.adapt_surge_ad_source(
            {"id": "yt", "surge_ad_kind": "youtube", "youtube_script_mode": "author-native"}, youtube())
        self.assertNotIn("script-response-body", native)
        self.assertEqual(report["required_sources"], [adapter.YOUTUBE_AUTHOR_QX])
        self.assertEqual(report["counts"]["output_rewrite_rules"], 2)

    def test_googlevideo_header_edit_matches_original_url_replacement(self):
        # Execute only our audited regex transformation over synthetic strings.
        # No downloaded JavaScript or source programs are evaluated.
        original = re.compile(adapter.YOUTUBE_HEADER_PATTERN.replace(r"\/", "/"))
        qx_regex = re.compile(adapter.QX_YOUTUBE_HEADER_MATCH)
        for scheme in ("http", "https"):
            for version in ("1.0", "1.1", "2"):
                for method in ("GET", "POST", "HEAD"):
                    target = "/videoplayback?foo=bar&ctier=L&one=a,two,ctier,last&three=3"
                    url = scheme + "://rr1---sn-example.googlevideo.com" + target
                    expected_url = original.sub(r"\1\2\3", url)
                    expected_target = expected_url.split(".com", 1)[1]
                    headers = method + " " + target + " HTTP/" + version + "\r\nHost: rr1---sn-example.googlevideo.com\r\nX-Test: &ctier=L&x=1,ctier,same\r\n"
                    changed = qx_regex.sub(r"\1\2\3\4", headers)
                    self.assertEqual(changed, method + " " + expected_target + " HTTP/" + version + "\r\nHost: rr1---sn-example.googlevideo.com\r\nX-Test: &ctier=L&x=1,ctier,same\r\n")
                    self.assertNotIn("url 302", changed)

    def test_header_edit_supports_absolute_form_and_leaves_header_fields_untouched(self):
        headers = "GET https://rr1.googlevideo.com/videoplayback?x=1&ctier=L&a=2,ctier,z HTTP/1.1\r\nHost: rr1.googlevideo.com\r\n"
        changed = re.sub(adapter.QX_YOUTUBE_HEADER_MATCH, r"\1\2\3\4", headers)
        self.assertEqual(changed, "GET https://rr1.googlevideo.com/videoplayback?x=1&a=2z HTTP/1.1\r\nHost: rr1.googlevideo.com\r\n")
        self.assertEqual(re.sub(adapter.QX_YOUTUBE_HEADER_MATCH, r"\1\2\3\4", headers.replace("ctier=L", "ctier=l")), headers.replace("ctier=L", "ctier=l"))

    def test_filename_can_identify_kind(self):
        native, _ = adapter.adapt_surge_ad_source({"id": "x", "url": "https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Module/Block/Advertising.sgmodule"}, advertising())
        self.assertIn("url reject", native)

    def test_unknown_sections_scripts_and_rule_changes_fail_closed(self):
        invalid = [
            advertising("[Script]\nx = type=http-response\n"),
            advertising().replace("[Rule]", "[Rule]\nDOMAIN,whole.example.com,REJECT"),
            advertising().replace("[Rule]", "[General]"),
            advertising().replace(" - reject", " _ REJECT-DICT", 1),
            advertising().replace("[Rule]", "#!include remote.sgmodule\n[Rule]"),
            advertising().replace("hostname = %APPEND%", "skip-server-cert-verify ="),
        ]
        for body in invalid:
            with self.subTest(body=body[:100]), self.assertRaises(ValueError):
                adapter.adapt_surge_ad_source({"id": "ad", "surge_ad_kind": "advertising"}, body)
        for body in (youtube().replace("DEST-PORT,443", "DEST-PORT,80"),
                     youtube().replace("$1$2$3 header", "$1$2 header"),
                     youtube().replace("binary-body-mode=1", "binary-body-mode=0"),
                     youtube().replace("max-size=2097152", "max-size=1024"),
                     youtube().replace("script-path=", "unsupported=true,script-path=")):
            with self.subTest(body=body[:100]), self.assertRaises(ValueError):
                adapter.adapt_surge_ad_source({"id": "yt", "surge_ad_kind": "youtube"}, body)

    def test_empty_html_or_unknown_identity_cannot_be_adapted(self):
        for source, body in (({"id": "x", "surge_ad_kind": "unknown"}, advertising()),
                             ({"id": "x", "surge_ad_kind": "youtube"}, "<html>error</html>"),
                             ({"id": "x", "surge_ad_kind": "advertising"}, ""),
                             ({"surge_ad_kind": "advertising"}, advertising())):
            with self.subTest(source=source), self.assertRaises(ValueError):
                adapter.adapt_surge_ad_source(source, body)


if __name__ == "__main__":
    unittest.main()
