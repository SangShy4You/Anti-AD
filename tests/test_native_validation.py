"""The native API exposes null providers during asynchronous initialization."""
import unittest

from scripts.validate_native import providers_ready


class NativeReadinessTests(unittest.TestCase):
    def test_null_missing_or_incomplete_providers_wait_for_the_expected_counts(self):
        expected = {"domains": 100, "extra": 3}
        for providers in ({}, {"domains": None, "extra": {"ruleCount": 3}},
                          {"domains": {"ruleCount": 0}, "extra": None},
                          {"domains": {"ruleCount": 100}, "extra": {"ruleCount": 2}}):
            with self.subTest(providers=providers):
                self.assertFalse(providers_ready(providers, expected))
        self.assertTrue(providers_ready(
            {"domains": {"ruleCount": 100}, "extra": {"ruleCount": 3}}, expected))


if __name__ == "__main__":
    unittest.main()
