"""Pin public GitHub dependencies without executing their downloaded contents.

The caller supplies a resolver when working from a reviewed, offline ref map.
Only ``resolve_ref`` performs network requests; credentials go exclusively to
api.github.com and redirects are deliberately rejected.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request


SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
GIST = re.compile(r"[0-9a-fA-F]{5,40}\Z")
SHORT_SHA = re.compile(r"[0-9a-fA-F]{7,39}\Z")
MAX_API_BYTES = 4 * 1024 * 1024


class DependencyError(ValueError):
    """A dependency could not be pinned while preserving its identity."""


def _sha(value: object) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise DependencyError("Resolver must return a full 40-character Git commit SHA")
    return value.lower()


def _repository(owner: str, repo: str) -> None:
    if not OWNER.fullmatch(owner) or not REPO.fullmatch(repo) or repo in {".", ".."}:
        raise DependencyError("Invalid public GitHub repository identity")


def _ref(value: str) -> str:
    decoded = urllib.parse.unquote(value)
    if not decoded or any(ord(char) < 32 for char in decoded) or "\\" in decoded:
        raise DependencyError("Invalid GitHub ref")
    if decoded.startswith("/") or any(part in {"", ".", ".."} for part in decoded.split("/")):
        raise DependencyError("Invalid GitHub ref")
    return decoded


def pin_url(url: str, resolver: Callable[[str], str]) -> str:
    """Return the same public GitHub file pinned to a complete commit SHA.

    Resolver keys are ``owner/repo@ref`` or ``gist:ID``. Gist URLs with an
    explicit abbreviated revision use ``gist:ID@REV``; resolving the latest
    revision for such a URL would silently change the requested content.
    Branch names containing a slash must URL-encode that slash (``a%2Fb``), as
    an unencoded raw URL cannot distinguish branch components from file paths.
    Query strings and fragments are retained exactly.
    """
    if not isinstance(url, str) or any(ord(char) < 32 for char in url):
        raise DependencyError("Dependency URL must be a public HTTPS GitHub file URL")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {
        "raw.githubusercontent.com", "github.com", "gist.githubusercontent.com"
    }:
        raise DependencyError("Only public HTTPS GitHub raw file URLs can be pinned")
    parts = parsed.path.split("/")
    if not parts or parts[0] != "" or any(not part for part in parts[1:]):
        raise DependencyError("Dependency URL does not identify a file")
    if any(urllib.parse.unquote(part) in {".", ".."} or
           "\\" in urllib.parse.unquote(part) or
           any(ord(char) < 32 for char in urllib.parse.unquote(part))
           for part in parts[1:]):
        raise DependencyError("Dependency URL contains a traversal component")
    if parsed.netloc == "gist.githubusercontent.com":
        if len(parts) not in {5, 6} or parts[3] != "raw":
            raise DependencyError("Expected a gist raw URL with a file name")
        owner, gist_id = parts[1:3]
        if not OWNER.fullmatch(owner) or not GIST.fullmatch(gist_id):
            raise DependencyError("Invalid public gist identity")
        if len(parts) == 5:
            commit, filename = _sha(resolver("gist:" + gist_id)), parts[4]
        else:
            revision, filename = parts[4:]
            if SHA.fullmatch(revision):
                commit = _sha(revision)
            elif SHORT_SHA.fullmatch(revision):
                commit = _sha(resolver(f"gist:{gist_id}@{revision}"))
                if not commit.startswith(revision.lower()):
                    raise DependencyError("Resolver changed the explicit gist revision")
            else:
                raise DependencyError("Invalid explicit gist revision")
        path = "/".join(["", owner, gist_id, "raw", commit, filename])
        return urllib.parse.urlunsplit(("https", "gist.githubusercontent.com", path, parsed.query, parsed.fragment))

    if parsed.netloc == "github.com":
        if len(parts) < 6 or parts[3] != "raw":
            raise DependencyError("Expected github.com/owner/repo/raw/ref/file")
        parts = parts[:3] + parts[4:]
    if len(parts) < 5:
        raise DependencyError("Expected raw.githubusercontent.com/owner/repo/ref/file")
    owner, repo = parts[1:3]
    _repository(owner, repo)
    rest = parts[3:]
    if rest[:2] in (["refs", "heads"], ["refs", "tags"]):
        rest = rest[2:]
    if len(rest) < 2:
        raise DependencyError("Dependency URL is missing its ref or file name")
    ref = _ref(rest[0])
    commit = _sha(ref) if SHA.fullmatch(ref) else _sha(resolver(f"{owner}/{repo}@{ref}"))
    path = "/".join(["", owner, repo, commit] + rest[1:])
    return urllib.parse.urlunsplit(("https", "raw.githubusercontent.com", path, parsed.query, parsed.fragment))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib may copy Authorization to redirects. Fail closed instead.
        raise DependencyError("GitHub API redirects are not followed")


def _api_json(path: str) -> dict:
    if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
        raise DependencyError("Invalid GitHub API path")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Anti-AD-QX-dependency-review/1",
        "Accept-Encoding": "identity",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request("https://api.github.com" + path, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200:
                raise DependencyError("GitHub API did not return HTTP 200")
            raw = response.read(MAX_API_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise DependencyError(f"GitHub API returned HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise DependencyError("GitHub API request failed") from None
    if len(raw) > MAX_API_BYTES:
        raise DependencyError("GitHub API response exceeds the size limit")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise DependencyError("GitHub API returned invalid JSON") from None
    if not isinstance(result, dict):
        raise DependencyError("GitHub API response must be an object")
    return result


def resolve_ref(key: str) -> str:
    """Resolve a public GitHub ref through its read-only official API.

    ``GITHUB_TOKEN`` is optional. This function never prints the token or
    follows redirects, and does not use credentials for raw-content hosts.
    """
    if not isinstance(key, str):
        raise DependencyError("Invalid dependency resolver key")
    if key.startswith("gist:"):
        gist_key = key[5:]
        gist_id, sep, revision = gist_key.partition("@")
        if not GIST.fullmatch(gist_id) or (sep and not (SHORT_SHA.fullmatch(revision) or SHA.fullmatch(revision))):
            raise DependencyError("Invalid gist resolver key")
        data = _api_json("/gists/" + gist_id + ("/" + revision if sep else ""))
        if data.get("public") is not True:
            raise DependencyError("Only public gist dependencies are supported")
        history = data.get("history")
        if not isinstance(history, list) or not history:
            raise DependencyError("GitHub gist response has no revision history")
        versions = [_sha(item.get("version")) for item in history if isinstance(item, dict)]
        if not versions:
            raise DependencyError("GitHub gist response has no valid revisions")
        if sep:
            candidates = [version for version in versions if version.startswith(revision.lower())]
            if len(candidates) != 1:
                raise DependencyError("GitHub gist revision is missing or ambiguous")
            return candidates[0]
        return versions[0]
    repository, sep, ref = key.rpartition("@")
    if not sep or repository.count("/") != 1:
        raise DependencyError("Expected an owner/repo@ref resolver key")
    owner, repo = repository.split("/")
    _repository(owner, repo)
    ref = _ref(ref)
    if SHA.fullmatch(ref):
        return _sha(ref)
    metadata = _api_json(f"/repos/{owner}/{repo}")
    if metadata.get("private") is not False:
        raise DependencyError("Only public repository dependencies are supported")
    data = _api_json(f"/repos/{owner}/{repo}/commits/" + urllib.parse.quote(ref, safe=""))
    return _sha(data.get("sha"))
