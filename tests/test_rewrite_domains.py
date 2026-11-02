"""Check that URL-only cleanup can never become an unintended blanket block."""

import unittest
import json

from scripts import compiler
from scripts.rewrite_domains import ExtractionError, audit_rule_source, extract_rule_source


FIXTURE = r"""#!name=Audited fragment
^https?:\/\/fc-video\.cdn\.bcebos\.com url reject
^https?:\/\/api\.htp\.ad-scope\.com\.cn.* url reject
^https?:\/\/sdk1xyajs\.data\.kuiniuca\.com url reject
^https?:\/\/stat\.peopleapp\.com\/ url reject
^https?:\/\/adapi\.izuiyou\.com\/ url reject
^https?:\/\/.+?\.kingsoft-office-service\.com url reject
^https?:\/\/.+\.pglstatp-toutiao\.com url reject
"""


class RewriteDomainTests(unittest.TestCase):
    def test_whole_rewrite_source_compiles_without_blocking_shared_business_apis(self):
        catalog = {"sources": [{"id": "reviewed", "role": "block", "enabled": True,
                   "source_format": "audited_qx_rewrite_domains", "expected_policy": "reject"}]}
        artifacts, report = compiler.compile_profile(catalog, {"reviewed": FIXTURE}, {})
        values = {json.loads(line.strip()[2:]) for line in artifacts["rules/ads-domain.yaml"].splitlines()
                  if line.strip().startswith("- ")}
        self.assertEqual(len(values), 7)
        self.assertIn(".kingsoft-office-service.com", values)
        self.assertNotIn("+.kingsoft-office-service.com", values)
        self.assertNotIn("api.m.jd.com", values)
        self.assertEqual(report["sources"][0]["derivation"]["count"], 7)

    def test_reviewed_hosts_and_children_only_scope_are_preserved(self):
        result = extract_rule_source(FIXTURE)
        values = [line for line in result.splitlines() if line and not line.startswith("#")]
        self.assertEqual(values, [
            "fc-video.cdn.bcebos.com", "api.htp.ad-scope.com.cn",
            "sdk1xyajs.data.kuiniuca.com", "stat.peopleapp.com", "adapi.izuiyou.com",
            ".kingsoft-office-service.com", ".pglstatp-toutiao.com",
        ])
        self.assertNotIn("kingsoft-office-service.com", values)
        self.assertNotIn("+.kingsoft-office-service.com", values)
        report = audit_rule_source(FIXTURE)
        self.assertEqual(report["count"], 7)
        self.assertEqual(report["entries"][-2]["scope"], "subdomains-only")
        self.assertEqual(report["entries"][0]["evidence"][0]["line"], 2)

    def test_new_hosts_paths_scripts_and_response_stubs_are_never_promoted(self):
        extra = r"""
^https?:\/\/new-ad.example\/ url reject
^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=start url reject
^https?:\/\/api\.zhihu\.com\/commercial_api\/launch_v2 url reject-dict
^https?:\/\/business.example url reject-200
^https?:\/\/api\.example\/ads url script-response-body https://example.invalid/ad.js
^https?:\/\/shared\.example url script-request-header https://example.invalid/ad.js
hostname = api.m.jd.com, api.zhihu.com, business.example
"""
        self.assertEqual(extract_rule_source(FIXTURE + extra), extract_rule_source(FIXTURE))

    def test_changed_reviewed_rule_cannot_silently_reduce_or_expand_scope(self):
        original = r"^https?:\/\/fc-video\.cdn\.bcebos\.com url reject"
        cases = [
            "", "# " + original,
            original.replace("url reject", "url reject-dict"),
            original.replace("url reject", "url reject-200"),
            original.replace("url reject", "url reject-img"),
            original.replace(" url reject", r"\/ads url reject"),
            original.replace(" url reject", " url script-response-body https://example.invalid/a.js"),
            original + " extra-argument",
            original.replace(r"fc-video\.cdn\.bcebos\.com", r".*\.bcebos\.com"),
        ]
        for replacement in cases:
            with self.subTest(replacement=replacement):
                with self.assertRaisesRegex(ExtractionError, "fc-video.cdn.bcebos.com"):
                    extract_rule_source(FIXTURE.replace(original, replacement))

    def test_comments_duplicate_evidence_and_source_order_do_not_change_output(self):
        lines = FIXTURE.splitlines()
        revised = "\ufeff# heading\n" + "\n".join(reversed(lines)) + "\n" + lines[1] + " # audited duplicate\n"
        self.assertEqual(extract_rule_source(revised), extract_rule_source(FIXTURE))
        self.assertEqual(len(audit_rule_source(revised)["entries"][0]["evidence"]), 2)
        with self.assertRaises(ExtractionError):
            extract_rule_source(FIXTURE + "\x00")


if __name__ == "__main__":
    unittest.main()
