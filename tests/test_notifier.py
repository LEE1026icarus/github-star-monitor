"""
Tests for src/notifier.py - Discord notification formatting and sending.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure the project root is on sys.path for absolute imports
sys.path.insert(0, os.path.expanduser("~/ai_team/workspace/github-star-monitor"))

from src.notifier import format_discord_message, send_discord_notification


class TestFormatDiscordMessage(unittest.TestCase):
    """Tests for format_discord_message()."""

    def setUp(self):
        """Sample repo data matching the expected input format from comparator.py."""
        self.sample_repos = [
            {
                "repo_name": "owner/repo",
                "stars": 4210,
                "star_delta": 842,
                "description": "AI coding agent framework",
                "language": "Python",
                "html_url": "https://github.com/owner/repo",
                "is_new": False,
            },
            {
                "repo_name": "another-org/awesome-project",
                "stars": 2103,
                "star_delta": 621,
                "description": "Lightweight Python async framework",
                "language": "Python",
                "html_url": "https://github.com/another-org/awesome-project",
                "is_new": False,
            },
            {
                "repo_name": "new-kid/on-the-block",
                "stars": 150,
                "star_delta": 150,
                "description": "Brand new hot repo",
                "language": "Rust",
                "html_url": "https://github.com/new-kid/on-the-block",
                "is_new": True,
            },
        ]

    def test_format_normal_input(self):
        """format_discord_message produces correct markdown output for normal input."""
        result = format_discord_message(self.sample_repos, delta_hours=12)

        # Header
        self.assertIn("🔥 GitHub 급상승 레포 Top 3", result)
        self.assertIn("/ 12h", result)

        # Repo 1 (not new)
        self.assertIn("1. owner/repo", result)
        self.assertIn("⭐ +842", result)
        self.assertIn("total 4,210", result)
        self.assertIn("AI coding agent framework", result)
        self.assertIn("github.com/owner/repo", result)
        # No 🆕 for non-new repos
        self.assertNotIn("🆕 1.", result)

        # Repo 2 (not new)
        self.assertIn("2. another-org/awesome-project", result)
        self.assertIn("⭐ +621", result)
        self.assertIn("total 2,103", result)

        # Repo 3 (new) — should have 🆕
        self.assertIn("3. 🆕 new-kid/on-the-block", result)
        self.assertIn("⭐ +150", result)
        self.assertIn("total 150", result)

    def test_empty_list(self):
        """format_discord_message handles an empty list gracefully."""
        result = format_discord_message([], delta_hours=12)
        self.assertIn("🔥 GitHub 급상승 레포 Top 0", result)
        # Should still have the header but no entries
        self.assertNotIn("1.", result)

    def test_missing_fields_graceful(self):
        """format_discord_message handles missing optional fields gracefully."""
        minimal_repos = [
            {
                "repo_name": "minimal/repo",
                "stars": 100,
                "star_delta": 50,
                # No description, no language, no html_url, no is_new
            }
        ]
        result = format_discord_message(minimal_repos, delta_hours=12)
        self.assertIn("1. minimal/repo", result)
        self.assertIn("⭐ +50", result)
        self.assertIn("total 100", result)
        # Should not have 설명 line (missing description)
        self.assertNotIn("설명:", result)
        # Should not crash
        self.assertIsInstance(result, str)

    def test_truncates_long_description(self):
        """format_discord_message truncates descriptions longer than 100 chars."""
        long_desc = "A" * 150
        repos = [
            {
                "repo_name": "test/repo",
                "stars": 100,
                "star_delta": 10,
                "description": long_desc,
                "language": "Go",
                "html_url": "https://github.com/test/repo",
                "is_new": False,
            }
        ]
        result = format_discord_message(repos, delta_hours=12)
        # The description should be truncated to 100 chars
        self.assertIn("A" * 100 + "...", result)
        self.assertNotIn("A" * 101, result)

    def test_new_repo_gets_emoji(self):
        """format_discord_message adds 🆕 emoji for repos where is_new is True."""
        repos = [
            {
                "repo_name": "old/repo",
                "stars": 500,
                "star_delta": 20,
                "description": "Old repo",
                "language": "JS",
                "html_url": "https://github.com/old/repo",
                "is_new": False,
            },
            {
                "repo_name": "new/repo",
                "stars": 300,
                "star_delta": 200,
                "description": "New repo",
                "language": "TS",
                "html_url": "https://github.com/new/repo",
                "is_new": True,
            },
        ]
        result = format_discord_message(repos, delta_hours=12)

        lines = result.split("\n")
        # Find the line for repo 1 (old) - should NOT have 🆕
        old_line = [l for l in lines if "1." in l and "old/repo" in l][0]
        self.assertNotIn("🆕", old_line)

        # Find the line for repo 2 (new) - should have 🆕
        new_line = [l for l in lines if "2." in l and "new/repo" in l][0]
        self.assertIn("🆕", new_line)

    def test_respects_1900_char_limit(self):
        """format_discord_message truncates to stay under 1900 characters."""
        # Create many repos with long descriptions to force truncation
        repos = []
        for i in range(30):
            repos.append({
                "repo_name": f"org/repo-{i:03d}",
                "stars": 1000 + i,
                "star_delta": 500 - i * 10,
                "description": f"This is repo number {i} with a somewhat detailed description that takes space",
                "language": "Python",
                "html_url": f"https://github.com/org/repo-{i:03d}",
                "is_new": i < 5,
            })

        result = format_discord_message(repos, delta_hours=12)
        self.assertLessEqual(len(result), 1900, f"Message length {len(result)} exceeds 1900 chars")

        # Should still have the header
        self.assertIn("🔥 GitHub 급상승 레포", result)

        # The Top N in header may differ from input length if truncated
        # But there should be at least some repos
        self.assertIn("1.", result)

    def test_skip_empty_description(self):
        """format_discord_message skips the 설명 line for empty/missing descriptions."""
        repos = [
            {
                "repo_name": "has-desc/repo",
                "stars": 200,
                "star_delta": 30,
                "description": "I have a description",
                "language": "Python",
                "html_url": "https://github.com/has-desc/repo",
                "is_new": False,
            },
            {
                "repo_name": "no-desc/repo",
                "stars": 100,
                "star_delta": 50,
                "description": "",
                "language": "Rust",
                "html_url": "https://github.com/no-desc/repo",
                "is_new": False,
            },
        ]
        result = format_discord_message(repos, delta_hours=12)

        # First repo should have 설명
        self.assertIn("설명: I have a description", result)

        # Second repo should NOT have 설명 line
        self.assertNotIn("설명:", result.split("2. ")[1].split("3. ")[0] if "3. " in result else result.split("2. ")[1])

    def test_empty_string_description_skipped(self):
        """Empty string description is treated same as missing — skipped."""
        repos = [
            {
                "repo_name": "empty-desc/repo",
                "stars": 50,
                "star_delta": 25,
                "description": "",
                "language": "C",
                "html_url": "https://github.com/empty-desc/repo",
                "is_new": False,
            }
        ]
        result = format_discord_message(repos, delta_hours=12)
        self.assertNotIn("설명:", result)


class TestSendDiscordNotification(unittest.TestCase):
    """Tests for send_discord_notification()."""

    def setUp(self):
        self.webhook_url = "https://discord.com/api/webhooks/123/abc"
        self.message = "Hello Discord!"

    @patch("src.notifier.requests.post")
    def test_send_success(self, mock_post):
        """send_discord_notification returns True on HTTP 2xx success."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        result = send_discord_notification(self.webhook_url, self.message)
        self.assertTrue(result)

        # Verify correct payload was sent
        mock_post.assert_called_once_with(
            self.webhook_url,
            json={"content": self.message},
            timeout=10,
        )

    @patch("src.notifier.requests.post")
    def test_send_200_success(self, mock_post):
        """send_discord_notification returns True on 200 OK as well."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = send_discord_notification(self.webhook_url, self.message)
        self.assertTrue(result)

    @patch("src.notifier.requests.post")
    def test_send_http_error_4xx(self, mock_post):
        """send_discord_notification returns False on HTTP 4xx errors."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        result = send_discord_notification(self.webhook_url, self.message)
        self.assertFalse(result)

    @patch("src.notifier.requests.post")
    def test_send_http_error_5xx(self, mock_post):
        """send_discord_notification returns False on HTTP 5xx errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        result = send_discord_notification(self.webhook_url, self.message)
        self.assertFalse(result)

    @patch("src.notifier.requests.post")
    def test_send_http_error_429(self, mock_post):
        """send_discord_notification returns False on rate limit (429)."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Too Many Requests"
        mock_post.return_value = mock_response

        result = send_discord_notification(self.webhook_url, self.message)
        self.assertFalse(result)

    @patch("src.notifier.requests.post")
    def test_send_connection_error(self, mock_post):
        """send_discord_notification returns False on connection error."""
        import requests as requests_lib

        mock_post.side_effect = requests_lib.ConnectionError("Connection refused")

        result = send_discord_notification(self.webhook_url, self.message)
        self.assertFalse(result)

    @patch("src.notifier.requests.post")
    def test_send_timeout(self, mock_post):
        """send_discord_notification returns False on timeout."""
        import requests as requests_lib

        mock_post.side_effect = requests_lib.Timeout("Request timed out")

        result = send_discord_notification(self.webhook_url, self.message)
        self.assertFalse(result)

    @patch("src.notifier.requests.post")
    def test_send_request_exception(self, mock_post):
        """send_discord_notification returns False on general RequestException."""
        import requests as requests_lib

        mock_post.side_effect = requests_lib.RequestException("Something went wrong")

        result = send_discord_notification(self.webhook_url, self.message)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
