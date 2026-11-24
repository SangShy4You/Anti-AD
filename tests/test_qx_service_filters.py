import unittest

from scripts.qx_filters import parse_filters
from scripts.qx_service_filters import prepare_service_filters


def source(url="https://raw.githubusercontent.com/example/r/main/service.list", **extra):
    return {"id":"service", "url":url, "force_policy":"Google", "service_selection":{
        "allowed_input_policies":["Original"], "allowed_selected_types":["host", "host-suffix", "ip-cidr", "user-agent"]}, **extra}


class ServiceFilterTests(unittest.TestCase):
    def test_raw_out_and_normalized_in_retain_exact_reviewed_endpoints(self):
        spec=source("https://raw.githubusercontent.com/example/r/main/service.list#out=IP-ASN%2C&in=api.example.com+files.example.com&hide=1&ntf=0")
        text,report=prepare_service_filters(spec,"HOST,api.example.com,Original\nHOST-SUFFIX,files.example.com,Original\nHOST,other.example.com,Original\nIP-ASN,12345,Original\n")
        self.assertEqual(text,"host, api.example.com, Google\nhost-suffix, files.example.com, Google\n")
        self.assertEqual(report["input_rules"],4)
        self.assertEqual(report["selected_rules"],2)
        self.assertEqual(report["out_key_counts"],{"IP-ASN,":1})

    def test_native_qualifiers_and_case_sensitive_agent_remain_intact(self):
        text,_=prepare_service_filters(source(),"HOST-SUFFIX,EXAMPLE.com,Original,extended-matching\nIP-CIDR,203.0.113.0/24,Original,no-resolve\nUSER-AGENT,AppCase*,Original\n")
        self.assertIn("host-suffix, example.com, Google, extended-matching",text)
        self.assertIn("ip-cidr, 203.0.113.0/24, Google, no-resolve",text)
        self.assertIn("user-agent, AppCase*, Google",text)

    def test_source_policy_and_selected_type_drift_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"policy changed"):
            prepare_service_filters(source(),"HOST,api.example.com,reject\n")
        with self.assertRaisesRegex(ValueError,"match type changed"):
            prepare_service_filters(source(),"IP-ASN,12345,Original\n")

    def test_only_explicit_verified_kop_options_are_removed(self):
        spec=source();spec["service_selection"]["kop_drop_options"]=["no-resolve","extended-matching"]
        text,report=prepare_service_filters(spec,"HOST-SUFFIX,example.com,Original,extended-matching\nIP-CIDR,203.0.113.0/24,Original,no-resolve,force-cellular\n")
        self.assertIn("ip-cidr, 203.0.113.0/24, Google, force-cellular",text)
        self.assertNotIn("no-resolve",text)
        self.assertEqual(report["kop_compatibility_dropped_options"],{"extended-matching":1,"no-resolve":1})
        spec["service_selection"]["kop_drop_options"]=["force-cellular"]
        with self.assertRaisesRegex(ValueError,"Unreviewed KOP"):
            prepare_service_filters(spec,"HOST,example.com,Original\n")

    def test_unknown_parser_parameters_and_empty_selection_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"Unsupported service selection"):
            prepare_service_filters(source("https://raw.githubusercontent.com/e/r/main/a#regex=.*"),"HOST,a.example.com,Original")
        with self.assertRaisesRegex(ValueError,"no rules"):
            prepare_service_filters(source("https://raw.githubusercontent.com/e/r/main/a#in=missing.example.com"),"HOST,a.example.com,Original")

    def test_surge_without_policy_is_valid_but_a_new_embedded_policy_is_not(self):
        spec=source();spec["service_selection"]["allowed_input_policies"]=[]
        text,_=prepare_service_filters(spec,"DOMAIN-SUFFIX,example.com\nIP-CIDR,203.0.113.0/24,no-resolve\n")
        self.assertIn("host-suffix, example.com, Google",text)
        with self.assertRaisesRegex(ValueError,"policy changed"):
            prepare_service_filters(spec,"DOMAIN,example.com,direct\n")

    def test_custom_geoip_labels_require_explicit_per_source_review(self):
        spec={"id":"n","source_format":"qx","force_policy":"proxy"}
        with self.assertRaisesRegex(ValueError,"unsupported GEOIP"):
            parse_filters(spec,"GEOIP,NETFLIX,no-resolve")
        model,_=parse_filters({**spec,"allowed_geoip_tags":["netflix"]},"GEOIP,NETFLIX,no-resolve")
        self.assertEqual(model[0].render(),"geoip, netflix, proxy, no-resolve")
        with self.assertRaisesRegex(ValueError,"unsupported GEOIP"):
            parse_filters({**spec,"allowed_geoip_tags":["netflix"]},"GEOIP,GOOGLE")


if __name__=="__main__":
    unittest.main()
