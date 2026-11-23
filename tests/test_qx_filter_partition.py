import fnmatch
import ipaddress
import unittest

from scripts.qx_filter_partition import partition_ordered_filters


def spec(output, kind, policies=None):
    return {"output": output, "name": output[:-5], "kind": kind,
            "allowed_policies": policies or (["reject"] if kind == "reject" else ["direct"])}


def active(text):
    return [line for line in text.splitlines(keepends=True) if line.strip() and not line.lstrip().startswith(("#", ";", "//"))]


def evaluate(rows, domain, ip="198.51.100.8", ua="Browser"):
    for row in rows:
        fields = [value.strip() for value in row.split(",")]
        kind, value, policy = fields[:3]
        matched = (kind == "host" and domain == value
                   or kind == "host-suffix" and (domain == value or domain.endswith("." + value))
                   or kind == "host-keyword" and value in domain
                   or kind == "host-wildcard" and fnmatch.fnmatchcase(domain, value)
                   or kind == "ip-cidr" and ipaddress.ip_address(ip) in ipaddress.ip_network(value)
                   or kind == "user-agent" and fnmatch.fnmatchcase(ua, value))
        if matched:
            return policy
    return "fallback"


class OrderedPartitionTests(unittest.TestCase):
    def test_ordered_partition_preserves_cases_that_global_action_buckets_break(self):
        body = ("# reviewed allow\nhost, safe.example.com, direct\n"
                "# advertising\nhost-suffix, example.com, reject\n"
                "host-suffix, metrics.other.test, reject\n"
                "# later allow must stay later\nhost-suffix, other.test, direct\n")
        specifications = [spec("allow-first.list", "preserve"), spec("ads-main.list", "reject"), spec("allow-last.list", "preserve")]
        products, imports, report = partition_ordered_filters(body, specifications)
        ordered = sum((active(products[item["output"]]) for item in imports), [])
        self.assertEqual(active(body), ordered)
        self.assertEqual([item["force_policy"] for item in imports], [None, "reject", None])
        self.assertTrue(report["source_body_reconstructed_exactly"])
        self.assertEqual(report["input_rules"], report["output_rules"])
        self.assertEqual(evaluate(ordered, "safe.example.com"), "direct")
        self.assertEqual(evaluate(ordered, "ads.example.com"), "reject")
        self.assertEqual(evaluate(ordered, "metrics.other.test"), "reject")
        self.assertEqual(evaluate(ordered, "mail.other.test"), "direct")
        rejects = [row for row in active(body) if row.split(",")[2].strip() == "reject"]
        allows = [row for row in active(body) if row.split(",")[2].strip() != "reject"]
        self.assertEqual(evaluate(rejects + allows, "safe.example.com"), "reject")
        self.assertEqual(evaluate(allows + rejects, "metrics.other.test"), "direct")

    def test_ip_user_agent_wildcard_keyword_and_options_are_not_approximated(self):
        body = ("# first\r\nhost-wildcard, safe?.example, proxy, force-remote-dns\r\n"
                "host-keyword, adsite, reject, via-interface=pdp_ip0\r\n"
                "ip-cidr, 203.0.113.0/24, reject, no-resolve\r\n"
                "user-agent, AVOS*, direct\r\n")
        products, imports, report = partition_ordered_filters(body, [spec("first.list", "preserve", ["proxy"]), spec("ads.list", "reject"), spec("last.list", "preserve")])
        rows = sum((active(products[item["output"]]) for item in imports), [])
        self.assertEqual(rows, active(body))
        for domain, ip, ua, expected in [("safe1.example", "203.0.113.8", "AVOSX", "proxy"), ("adsite.example", "198.51.100.8", "AVOSX", "reject"), ("ordinary.test", "203.0.113.8", "AVOSX", "reject"), ("ordinary.test", "198.51.100.8", "AVOSX", "direct")]:
            self.assertEqual(evaluate(rows, domain, ip, ua), expected)
        self.assertEqual(report["input_rules"], 4)

    def test_non_plain_reject_variant_retains_original_action_and_is_never_forced(self):
        body = "host, blackhole.example, reject-drop\nhost, advert.example, reject\n"
        products, imports, _ = partition_ordered_filters(body, [spec("special.list", "preserve", ["reject-drop"]), spec("normal.list", "reject")])
        self.assertIsNone(imports[0]["force_policy"])
        self.assertIn("reject-drop", products["special.list"])
        self.assertEqual(imports[1]["force_policy"], "reject")

    def test_added_or_removed_run_or_unreviewed_policy_fails_closed(self):
        specifications = [spec("first.list", "preserve"), spec("ads.list", "reject")]
        for body, message in [
            ("host,a.test,direct\nhost,b.test,reject\nhost,c.test,direct\n", "topology"),
            ("host,a.test,reject\n", "topology"),
            ("host,a.test,unreviewed-policy\nhost,b.test,reject\n", "policy changed"),
            ("host,a.test,direct\nhost,b.test,reject-drop\n", "topology"),
        ]:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, message):
                partition_ordered_filters(body, specifications)

    def test_invalid_or_ambiguous_resource_contract_is_rejected(self):
        valid = spec("first.list", "preserve")
        invalid_specs = [[], [dict(valid, output="../escape.list")], [valid, dict(valid)],
                         [dict(valid, kind="unknown")], [dict(valid, name="unsafe, name")],
                         [dict(valid, allowed_policies=["direct", "direct"])],
                         [dict(valid, allowed_policies=["reject"])],
                         [dict(valid, force_policy="reject")],
                         [spec("ads.list", "reject", ["direct"])]]
        for specifications in invalid_specs:
            with self.subTest(specifications=specifications), self.assertRaises(ValueError):
                partition_ordered_filters("host,safe.test,direct\n", specifications)

    def test_unsupported_or_empty_source_does_not_emit_a_resource(self):
        for body in ("", "# no active rules\n", "process-name, ExampleApp, reject\n", "\ufeffhost,advert.test,reject\n"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                partition_ordered_filters(body, [spec("ads.list", "reject")])

    def test_source_and_contract_are_not_mutated_and_output_is_deterministic(self):
        body = "# heading\nhost,safe.test,direct\n\n# trailer\n"
        specifications = [spec("safe.list", "preserve")]
        before = repr(specifications)
        result = partition_ordered_filters(body, specifications)
        self.assertEqual(result, partition_ordered_filters(body, specifications))
        self.assertEqual(repr(specifications), before)
        self.assertEqual(active(result[0]["safe.list"]), active(body))


if __name__ == "__main__":
    unittest.main()
