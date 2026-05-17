"""
TDD tests for src/fetcher.py — GitHub Star Surge Monitor.

Tests use mocked requests.get to avoid real API calls.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

import requests as real_requests  # for exception types

# Ensure the project root is on sys.path so we can import src.fetcher
sys.path.insert(0, os.path.expanduser("~/ai_team/workspace/github-star-monitor"))

from src.fetcher import fetch_trending_repos, fetch_repo_details, enrich_trending_repos


# ---------------------------------------------------------------------------
# Mock response helpers
# ---------------------------------------------------------------------------

def _mock_oss_insight_response(rows=None):
    """Return a MagicMock that simulates a successful OSS Insight API response."""
    if rows is None:
        rows = [
            {
                "repo_id": 10270250,
                "repo_name": "torvalds/linux",
                "stars": 4210,
                "description": "Linux kernel source tree",
                "primary_language": "C",
            },
            {
                "repo_id": 21289110,
                "repo_name": "microsoft/vscode",
                "stars": 3890,
                "description": "Visual Studio Code",
                "primary_language": "TypeScript",
            },
            {
                "repo_id": 63476337,
                "repo_name": "oven-sh/bun",
                "stars": 5600,
                "description": "Incredibly fast JavaScript runtime",
                "primary_language": "Zig",
            },
        ]

    data = {
        "columns": [
            "repo_id",
            "repo_name",
            "stars",
            "description",
            "primary_language",
        ],
        "rows": rows,
    }

    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


def _mock_github_response(owner="torvalds", repo="linux", overrides=None):
    """Return a MagicMock that simulates a successful GitHub API response."""
    data = {
        "full_name": f"{owner}/{repo}",
        "stargazers_count": 185000,
        "description": "Linux kernel source tree",
        "language": "C",
        "html_url": f"https://github.com/{owner}/{repo}",
        "topics": ["linux", "kernel"],
        "created_at": "2011-09-04T19:44:19Z",
        "pushed_at": "2025-05-18T01:30:00Z",
        "license": {"spdx_id": "GPL-2.0"},
    }
    if overrides:
        data.update(overrides)

    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


def _mock_error_response(status_code, reason=""):
    """Return a MagicMock that simulates an error HTTP response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.reason = reason
    mock.json.side_effect = ValueError("No JSON")
    # raise_for_status should raise a real requests.HTTPError so that
    # `except requests.RequestException` catches it (TDD).
    http_error = real_requests.HTTPError(f"{status_code} {reason}")
    mock.raise_for_status.side_effect = http_error
    return mock


# ---------------------------------------------------------------------------
# Tests: fetch_trending_repos
# ---------------------------------------------------------------------------

class TestFetchTrendingRepos(unittest.TestCase):
    """Tests for fetch_trending_repos()."""

    @patch("src.fetcher.requests.get")
    def test_returns_correct_list_from_mock_response(self, mock_get):
        """Happy path — parsed OSS Insight response yields expected records."""
        mock_get.return_value = _mock_oss_insight_response()

        repos = fetch_trending_repos(period="past_24_hours", limit=30)

        self.assertIsInstance(repos, list)
        self.assertEqual(len(repos), 3)

        # Verify shape of each record
        for repo in repos:
            self.assertIn("repo_name", repo)
            self.assertIn("stars", repo)
            self.assertIn("description", repo)
            self.assertIn("primary_language", repo)

        self.assertEqual(repos[0]["repo_name"], "torvalds/linux")
        self.assertEqual(repos[0]["stars"], 4210)

    @patch("src.fetcher.requests.get")
    def test_respects_limit_argument(self, mock_get):
        """When limit=1, only 1 repo is returned."""
        mock_get.return_value = _mock_oss_insight_response()

        repos = fetch_trending_repos(limit=1)

        self.assertEqual(len(repos), 1)

    @patch("src.fetcher.requests.get")
    def test_handles_empty_rows(self, mock_get):
        """Empty rows list returns an empty list."""
        mock_get.return_value = _mock_oss_insight_response(rows=[])

        repos = fetch_trending_repos()

        self.assertEqual(repos, [])

    @patch("src.fetcher.requests.get")
    def test_handles_http_error(self, mock_get):
        """HTTP error from OSS Insight returns empty list (graceful degradation)."""
        mock_get.return_value = _mock_error_response(500, "Internal Server Error")

        repos = fetch_trending_repos()

        self.assertEqual(repos, [])

    @patch("src.fetcher.requests.get")
    def test_handles_invalid_json(self, mock_get):
        """Malformed JSON returns empty list."""
        mock = MagicMock()
        mock.status_code = 200
        mock.json.side_effect = ValueError("Expecting value: line 1 column 1")
        mock.raise_for_status.return_value = None
        mock_get.return_value = mock

        repos = fetch_trending_repos()

        self.assertEqual(repos, [])

    @patch("src.fetcher.requests.get")
    def test_passes_correct_query_params(self, mock_get):
        """Verify period is sent as a query parameter."""
        mock_get.return_value = _mock_oss_insight_response()

        fetch_trending_repos(period="past_7_days")

        # requests.get(url, params={...}) – params are in kwargs, not the URL string
        call_kwargs = mock_get.call_args[1]
        self.assertIn("params", call_kwargs)
        self.assertEqual(call_kwargs["params"], {"period": "past_7_days"})

    @patch("src.fetcher.requests.get")
    def test_handles_partial_keys_missing_in_rows(self, mock_get):
        """Rows missing some keys still work — missing keys become None or are skipped."""
        rows = [
            {
                "repo_id": 1,
                "repo_name": "a/b",
                # stars, description, primary_language missing
            }
        ]
        mock_get.return_value = _mock_oss_insight_response(rows=rows)

        repos = fetch_trending_repos()

        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["repo_name"], "a/b")


# ---------------------------------------------------------------------------
# Tests: fetch_repo_details
# ---------------------------------------------------------------------------

class TestFetchRepoDetails(unittest.TestCase):
    """Tests for fetch_repo_details()."""

    @patch("src.fetcher.requests.get")
    def test_returns_correct_dict_from_github_response(self, mock_get):
        """Happy path — GitHub API response is parsed to the expected dict."""
        mock_get.return_value = _mock_github_response("torvalds", "linux")

        details = fetch_repo_details("torvalds", "linux", "fake-token")

        self.assertIsInstance(details, dict)
        self.assertEqual(details["full_name"], "torvalds/linux")
        self.assertEqual(details["stargazers_count"], 185000)
        self.assertEqual(details["description"], "Linux kernel source tree")
        self.assertEqual(details["language"], "C")
        self.assertEqual(details["html_url"], "https://github.com/torvalds/linux")
        self.assertEqual(details["topics"], ["linux", "kernel"])
        self.assertEqual(details["created_at"], "2011-09-04T19:44:19Z")
        self.assertEqual(details["pushed_at"], "2025-05-18T01:30:00Z")
        self.assertEqual(details["license"], "GPL-2.0")

    @patch("src.fetcher.requests.get")
    def test_returns_none_on_404(self, mock_get):
        """GitHub 404 → returns None."""
        mock_get.return_value = _mock_error_response(404, "Not Found")

        details = fetch_repo_details("nonexistent", "repo", "fake-token")
        self.assertIsNone(details)

    @patch("src.fetcher.requests.get")
    def test_returns_none_on_rate_limit_403(self, mock_get):
        """GitHub 403 (rate limit) → returns None."""
        mock_get.return_value = _mock_error_response(403, "rate limit exceeded")

        details = fetch_repo_details("busy", "repo", "fake-token")
        self.assertIsNone(details)

    @patch("src.fetcher.requests.get")
    def test_returns_none_on_429(self, mock_get):
        """GitHub 429 (rate limit) → returns None."""
        mock_get.return_value = _mock_error_response(429, "Too Many Requests")

        details = fetch_repo_details("busy", "repo", "fake-token")
        self.assertIsNone(details)

    @patch("src.fetcher.requests.get")
    def test_uses_bearer_auth_header(self, mock_get):
        """Verify Authorization: Bearer header is set."""
        mock_get.return_value = _mock_github_response("torvalds", "linux")

        fetch_repo_details("torvalds", "linux", "my-secret-token")

        headers = mock_get.call_args[1].get("headers", {})
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer my-secret-token")

    @patch("src.fetcher.requests.get")
    def test_uses_user_agent_header(self, mock_get):
        """Verify User-Agent header is set."""
        mock_get.return_value = _mock_github_response("torvalds", "linux")

        fetch_repo_details("torvalds", "linux", "fake-token")

        headers = mock_get.call_args[1].get("headers", {})
        self.assertIn("User-Agent", headers)

    @patch("src.fetcher.requests.get")
    def test_null_license_handled(self, mock_get):
        """When license is null in GitHub response, license key is None."""
        mock_get.return_value = _mock_github_response(
            "owner", "repo", overrides={"license": None}
        )

        details = fetch_repo_details("owner", "repo", "fake-token")
        self.assertIsNone(details["license"])

    @patch("src.fetcher.requests.get")
    def test_constructs_correct_url(self, mock_get):
        """Verify the GitHub API URL is constructed correctly."""
        mock_get.return_value = _mock_github_response("myorg", "myrepo")

        fetch_repo_details("myorg", "myrepo", "token")

        url = mock_get.call_args[0][0]
        self.assertEqual(url, "https://api.github.com/repos/myorg/myrepo")


# ---------------------------------------------------------------------------
# Tests: enrich_trending_repos
# ---------------------------------------------------------------------------

class TestEnrichTrendingRepos(unittest.TestCase):
    """Tests for enrich_trending_repos()."""

    def _make_trending(self):
        return [
            {
                "repo_name": "torvalds/linux",
                "stars": 4210,
                "description": "Linux kernel source tree",
                "primary_language": "C",
            },
            {
                "repo_name": "microsoft/vscode",
                "stars": 3890,
                "description": "VS Code",
                "primary_language": "TypeScript",
            },
        ]

    def _make_github_details(self):
        return {
            "full_name": "torvalds/linux",
            "stargazers_count": 185000,
            "description": "Linux kernel source tree",
            "language": "C",
            "html_url": "https://github.com/torvalds/linux",
            "topics": ["linux", "kernel"],
            "created_at": "2011-09-04T19:44:19Z",
            "pushed_at": "2025-05-18T01:30:00Z",
            "license": "GPL-2.0",
        }

    @patch("src.fetcher.fetch_repo_details")
    def test_merges_data_correctly(self, mock_fetch_details):
        """Each trending record gets enriched with GitHub details."""
        mock_fetch_details.return_value = self._make_github_details()

        trending = self._make_trending()
        enriched = enrich_trending_repos(trending, "fake-token")

        self.assertEqual(len(enriched), 2)

        for repo in enriched:
            self.assertIn("repo_name", repo)
            self.assertIn("stars", repo)
            self.assertIn("description", repo)
            self.assertIn("language", repo)
            self.assertIn("html_url", repo)
            self.assertIn("topics", repo)
            self.assertIn("created_at", repo)
            self.assertIn("pushed_at", repo)
            self.assertIn("license", repo)

        # First repo should have GitHub-enriched fields
        self.assertEqual(enriched[0]["html_url"], "https://github.com/torvalds/linux")
        self.assertEqual(enriched[0]["topics"], ["linux", "kernel"])
        self.assertEqual(enriched[0]["license"], "GPL-2.0")

    @patch("src.fetcher.fetch_repo_details")
    def test_skips_failed_fetches(self, mock_fetch_details):
        """When fetch_repo_details returns None, that repo is omitted."""
        # First call returns details, second returns None (failed)
        mock_fetch_details.side_effect = [
            self._make_github_details(),
            None,
        ]

        trending = self._make_trending()
        enriched = enrich_trending_repos(trending, "fake-token")

        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0]["repo_name"], "torvalds/linux")

    @patch("src.fetcher.fetch_repo_details")
    def test_handles_exception_during_fetch(self, mock_fetch_details):
        """If fetch_repo_details raises an exception, that repo is skipped."""
        mock_fetch_details.side_effect = Exception("Connection timeout")

        trending = self._make_trending()
        enriched = enrich_trending_repos(trending, "fake-token")

        self.assertEqual(enriched, [])

    @patch("src.fetcher.fetch_repo_details")
    def test_splits_owner_repo_correctly(self, mock_fetch_details):
        """Verify owner and repo are extracted from 'owner/repo' format."""
        mock_fetch_details.return_value = self._make_github_details()

        trending = [
            {
                "repo_name": "a/b",
                "stars": 10,
                "description": "desc",
                "primary_language": "Rust",
            }
        ]

        enrich_trending_repos(trending, "token")

        mock_fetch_details.assert_called_once_with("a", "b", "token")

    @patch("src.fetcher.fetch_repo_details")
    def test_handles_repo_name_without_slash(self, mock_fetch_details):
        """Repo names without '/' should be skipped gracefully."""
        mock_fetch_details.return_value = self._make_github_details()

        trending = [
            {
                "repo_name": "invalidrepo",
                "stars": 10,
                "description": "desc",
                "primary_language": "Rust",
            }
        ]

        enriched = enrich_trending_repos(trending, "token")

        # Should be empty since we can't split owner/repo
        self.assertEqual(enriched, [])


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
