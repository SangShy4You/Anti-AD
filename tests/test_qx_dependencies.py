"""Dependency pins preserve revisions and never leak API credentials."""

import io
import json
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

from scripts import qx_dependencies as deps


COMMIT = "0123456789abcdef0123456789abcdef01234567"
OTHER = "f" * 40
GIST_ID = "f5f780d0f56b319b6ad9848fd080bb18"


class FakeResponse(io.BytesIO):
    status = 200


class PinUrlTests(unittest.TestCase):
    def test_repository_url_forms_share_one_canonical_pin(self):
        urls = [
            "https://raw.githubusercontent.com/owner/repo/main/a/b.js",
            "https://github.com/owner/repo/raw/main/a/b.js",
            "https://raw.githubusercontent.com/owner/repo/refs/heads/main/a/b.js",
            "https://github.com/owner/repo/raw/refs/heads/main/a/b.js",
            "https://raw.githubusercontent.com/owner/repo/refs/tags/main/a/b.js",
        ]
        for url in urls:
            with self.subTest(url=url):
                resolver = Mock(return_value=COMMIT)
                self.assertEqual(deps.pin_url(url, resolver),
                                 f"https://raw.githubusercontent.com/owner/repo/{COMMIT}/a/b.js")
                resolver.assert_called_once_with("owner/repo@main")

    def test_branch_slash_can_be_encoded_and_url_arguments_survive(self):
        resolver = Mock(return_value=COMMIT)
        url = "https://raw.githubusercontent.com/owner/repo/feature%2Fads/a%20b.js?raw=1&x=%2F#out=Hant&arg=one"
        self.assertEqual(deps.pin_url(url, resolver),
                         f"https://raw.githubusercontent.com/owner/repo/{COMMIT}/a%20b.js?raw=1&x=%2F#out=Hant&arg=one")
        resolver.assert_called_once_with("owner/repo@feature/ads")

    def test_full_repository_commit_bypasses_resolver(self):
        resolver = Mock(side_effect=AssertionError("must not resolve existing commits"))
        url = f"https://github.com/owner/repo/raw/{COMMIT.upper()}/a.js#test"
        self.assertEqual(deps.pin_url(url, resolver),
                         f"https://raw.githubusercontent.com/owner/repo/{COMMIT}/a.js#test")
        resolver.assert_not_called()

    def test_unversioned_gist_is_pinned_without_losing_file_or_arguments(self):
        resolver = Mock(return_value=COMMIT)
        url = f"https://gist.githubusercontent.com/owner/{GIST_ID}/raw/a.min.js?x=1#out=Hant"
        self.assertEqual(deps.pin_url(url, resolver),
                         f"https://gist.githubusercontent.com/owner/{GIST_ID}/raw/{COMMIT}/a.min.js?x=1#out=Hant")
        resolver.assert_called_once_with("gist:" + GIST_ID)

    def test_full_gist_commit_needs_no_resolver(self):
        resolver = Mock(side_effect=AssertionError("must not resolve"))
        url = f"https://gist.githubusercontent.com/owner/{GIST_ID}/raw/{COMMIT}/a.js"
        self.assertEqual(deps.pin_url(url, resolver), url)
        resolver.assert_not_called()

    def test_abbreviated_gist_revision_is_never_replaced_with_latest(self):
        resolver = Mock(return_value=COMMIT)
        url = f"https://gist.githubusercontent.com/owner/{GIST_ID}/raw/{COMMIT[:8]}/a.js"
        self.assertEqual(deps.pin_url(url, resolver),
                         f"https://gist.githubusercontent.com/owner/{GIST_ID}/raw/{COMMIT}/a.js")
        resolver.assert_called_once_with(f"gist:{GIST_ID}@{COMMIT[:8]}")
        with self.assertRaisesRegex(deps.DependencyError, "changed the explicit"):
            deps.pin_url(url, lambda key: OTHER)

    def test_invalid_hosts_transports_and_paths_fail_before_resolution(self):
        invalid = [
            "http://raw.githubusercontent.com/owner/repo/main/a.js",
            "https://raw.githubusercontent.com.evil.test/owner/repo/main/a.js",
            "https://user@raw.githubusercontent.com/owner/repo/main/a.js",
            "https://raw.githubusercontent.com:443/owner/repo/main/a.js",
            "https://github.com/owner/repo/blob/main/a.js",
            "https://raw.githubusercontent.com/owner/repo/main",
            "https://raw.githubusercontent.com/owner/repo/refs/heads/main",
            "https://raw.githubusercontent.com/owner/repo/main/a/../b.js",
            "https://raw.githubusercontent.com/owner/repo/main/a/%2e%2e/b.js",
            "https://raw.githubusercontent.com/owner/repo/main/a/%00.js",
            "https://raw.githubusercontent.com/owner/repo/main/a%5Cb.js",
            "https://raw.githubusercontent.com/owner/repo/main//a.js",
            f"https://gist.githubusercontent.com/owner/{GIST_ID}/raw",
            f"https://gist.githubusercontent.com/owner/{GIST_ID}/raw/invalid/a.js",
        ]
        resolver = Mock(side_effect=AssertionError("invalid URL must fail first"))
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(deps.DependencyError):
                deps.pin_url(url, resolver)
        resolver.assert_not_called()

    def test_resolver_must_supply_full_commit(self):
        url = "https://raw.githubusercontent.com/owner/repo/main/a.js"
        for value in (None, "main", COMMIT[:8], "g" * 40, {"sha": COMMIT}):
            with self.subTest(value=value), self.assertRaises(deps.DependencyError):
                deps.pin_url(url, lambda key: value)


class ResolveRefTests(unittest.TestCase):
    @patch.object(deps, "_api_json")
    def test_repository_is_checked_public_then_resolved(self, read):
        read.side_effect = [{"private": False}, {"sha": COMMIT}]
        self.assertEqual(deps.resolve_ref("owner/repo@feature/ads"), COMMIT)
        self.assertEqual(read.call_args_list,
                         [unittest.mock.call("/repos/owner/repo"),
                          unittest.mock.call("/repos/owner/repo/commits/feature%2Fads")])

    @patch.object(deps, "_api_json")
    def test_private_repository_and_missing_visibility_are_rejected(self, read):
        for metadata in ({"private": True}, {}):
            read.reset_mock()
            read.return_value = metadata
            with self.subTest(metadata=metadata), self.assertRaisesRegex(deps.DependencyError, "Only public"):
                deps.resolve_ref("owner/repo@main")
            read.assert_called_once_with("/repos/owner/repo")

    @patch.object(deps, "_api_json")
    def test_existing_repository_commit_does_not_need_network(self, read):
        self.assertEqual(deps.resolve_ref("owner/repo@" + COMMIT.upper()), COMMIT)
        read.assert_not_called()

    @patch.object(deps, "_api_json")
    def test_latest_public_gist_revision_is_used(self, read):
        read.return_value = {"public": True, "history": [{"version": COMMIT}, {"version": OTHER}]}
        self.assertEqual(deps.resolve_ref("gist:" + GIST_ID), COMMIT)
        read.assert_called_once_with("/gists/" + GIST_ID)

    @patch.object(deps, "_api_json")
    def test_explicit_gist_revision_is_found_without_using_newer_history(self, read):
        read.return_value = {"public": True, "history": [{"version": OTHER}, {"version": COMMIT}]}
        self.assertEqual(deps.resolve_ref(f"gist:{GIST_ID}@{COMMIT[:8]}"), COMMIT)
        read.assert_called_once_with(f"/gists/{GIST_ID}/{COMMIT[:8]}")

    @patch.object(deps, "_api_json")
    def test_invalid_gist_state_or_missing_revision_fails(self, read):
        for data in ({"public": False, "history": [{"version": COMMIT}]},
                     {"public": True, "history": []},
                     {"public": True, "history": [{"version": "bad"}]}):
            read.return_value = data
            with self.subTest(data=data), self.assertRaises(deps.DependencyError):
                deps.resolve_ref("gist:" + GIST_ID)
        read.return_value = {"public": True, "history": [{"version": OTHER}]}
        with self.assertRaisesRegex(deps.DependencyError, "missing or ambiguous"):
            deps.resolve_ref(f"gist:{GIST_ID}@{COMMIT[:8]}")

    @patch.object(deps, "_api_json")
    def test_invalid_keys_never_make_requests(self, read):
        for key in (None, "https://evil.test", "owner/repo", "owner/../repo@main",
                    "owner/repo@../main", "gist:../evil", "gist:" + GIST_ID + "@invalid"):
            with self.subTest(key=key), self.assertRaises(deps.DependencyError):
                deps.resolve_ref(key)
        read.assert_not_called()


class ApiBoundaryTests(unittest.TestCase):
    @patch.object(deps.urllib.request, "build_opener")
    def test_token_goes_only_to_official_api_with_redirect_blocker(self, build):
        opener = build.return_value
        opener.open.return_value = FakeResponse(json.dumps({"sha": COMMIT}).encode())
        with patch.dict(deps.os.environ, {"GITHUB_TOKEN": "unit-test-secret"}):
            self.assertEqual(deps._api_json("/repos/owner/repo/commits/main"), {"sha": COMMIT})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/repos/owner/repo/commits/main")
        self.assertEqual(request.get_header("Authorization"), "Bearer unit-test-secret")
        self.assertIsInstance(build.call_args.args[0], deps._NoRedirect)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 30)

    @patch.object(deps.urllib.request, "build_opener")
    def test_anonymous_request_does_not_create_authorization_header(self, build):
        build.return_value.open.return_value = FakeResponse(b'{}')
        with patch.dict(deps.os.environ, {}, clear=True):
            deps._api_json("/gists/" + GIST_ID)
        self.assertIsNone(build.return_value.open.call_args.args[0].get_header("Authorization"))

    def test_cross_host_redirect_is_rejected_without_a_second_request(self):
        handler = deps._NoRedirect()
        request = urllib.request.Request("https://api.github.com/repos/owner/repo", headers={"Authorization": "Bearer secret"})
        with self.assertRaisesRegex(deps.DependencyError, "redirects"):
            handler.redirect_request(request, None, 302, "Found", {}, "https://evil.test/receive")

    @patch.object(deps.urllib.request, "build_opener")
    def test_api_failures_are_redacted_and_fail_closed(self, build):
        for error in (urllib.error.HTTPError("https://api.github.com/x", 403, "secret", {}, None),
                      urllib.error.URLError("unit-test-secret")):
            build.return_value.open.side_effect = error
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(deps.DependencyError) as caught:
                    deps._api_json("/repos/owner/repo")
                self.assertNotIn("secret", str(caught.exception))

    @patch.object(deps.urllib.request, "build_opener")
    def test_api_size_and_json_validation(self, build):
        for payload in (b'not json', b'[]', b'x' * (deps.MAX_API_BYTES + 1)):
            build.return_value.open.return_value = FakeResponse(payload)
            with self.subTest(length=len(payload)), self.assertRaises(deps.DependencyError):
                deps._api_json("/repos/owner/repo")


if __name__ == "__main__":
    unittest.main()
