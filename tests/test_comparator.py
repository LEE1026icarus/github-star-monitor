"""Tests for src/comparator.py — star delta computation and snapshot management."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.expanduser("~/ai_team/workspace/github-star-monitor"))

from src.comparator import (
    build_snapshot,
    compute_star_deltas,
    get_top_n,
    load_snapshot,
    save_snapshot,
)


class TestLoadSnapshot(unittest.TestCase):
    """Tests for load_snapshot()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmpdir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.tmpdir)

    def test_load_existing_file(self):
        """load_snapshot returns parsed dict for valid JSON file."""
        path = os.path.join(self.tmpdir, "snapshot.json")
        data = {"timestamp": "2026-01-01T00:00:00Z", "repos": {}}
        with open(path, "w") as f:
            json.dump(data, f)
        result = load_snapshot(path)
        self.assertEqual(result, data)

    def test_load_absent_file(self):
        """load_snapshot returns None when file does not exist."""
        path = os.path.join(self.tmpdir, "nonexistent.json")
        result = load_snapshot(path)
        self.assertIsNone(result)

    def test_load_empty_file(self):
        """load_snapshot returns None for empty file."""
        path = os.path.join(self.tmpdir, "empty.json")
        with open(path, "w") as f:
            pass
        result = load_snapshot(path)
        self.assertIsNone(result)

    def test_load_invalid_json(self):
        """load_snapshot returns None for malformed JSON."""
        path = os.path.join(self.tmpdir, "bad.json")
        with open(path, "w") as f:
            f.write("not valid json {{{")
        result = load_snapshot(path)
        self.assertIsNone(result)

    def test_load_directory_path(self):
        """load_snapshot returns None when path is a directory."""
        result = load_snapshot(self.tmpdir)
        self.assertIsNone(result)


class TestSaveSnapshot(unittest.TestCase):
    """Tests for save_snapshot()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmpdir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.tmpdir)

    def test_save_and_load_roundtrip(self):
        """save_snapshot writes valid JSON that load_snapshot can read back."""
        path = os.path.join(self.tmpdir, "snapshot.json")
        data = {
            "timestamp": "2026-05-18T00:00:00Z",
            "repos": {
                "owner/repo": {
                    "stars": 4210,
                    "description": "AI coding agent framework",
                    "language": "Python",
                    "url": "https://github.com/owner/repo",
                }
            },
        }
        save_snapshot(data, path)
        self.assertTrue(os.path.isfile(path))
        loaded = load_snapshot(path)
        self.assertEqual(loaded, data)

    def test_creates_parent_directories(self):
        """save_snapshot creates intermediate dirs if they don't exist."""
        path = os.path.join(self.tmpdir, "sub", "deep", "snap.json")
        data = {"timestamp": "2026-01-01T00:00:00Z", "repos": {}}
        save_snapshot(data, path)
        self.assertTrue(os.path.isfile(path))
        loaded = load_snapshot(path)
        self.assertEqual(loaded, data)


class TestComputeStarDeltas(unittest.TestCase):
    """Tests for compute_star_deltas()."""

    def test_normal_case_mixed(self):
        """Some repos new, some existing with previous star counts."""
        current = [
            {
                "repo_name": "owner/repo1",
                "stars": 5000,
                "description": "Desc 1",
                "language": "Python",
                "html_url": "https://github.com/owner/repo1",
                "topics": ["ai"],
                "created_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-05-17T12:00:00Z",
                "license": "MIT",
            },
            {
                "repo_name": "owner/repo2",
                "stars": 200,
                "description": "Desc 2",
                "language": "Go",
                "html_url": "https://github.com/owner/repo2",
                "topics": ["cli"],
                "created_at": "2026-02-01T00:00:00Z",
                "pushed_at": "2026-05-16T12:00:00Z",
                "license": "Apache-2.0",
            },
            {
                "repo_name": "owner/repo3",
                "stars": 8500,
                "description": "Desc 3",
                "language": "Rust",
                "html_url": "https://github.com/owner/repo3",
                "topics": ["systems"],
                "created_at": "2026-03-01T00:00:00Z",
                "pushed_at": "2026-05-15T12:00:00Z",
                "license": "MIT",
            },
        ]
        previous = {
            "timestamp": "2026-05-17T00:00:00Z",
            "repos": {
                "owner/repo1": {"stars": 4500, "description": "Desc 1", "language": "Python", "url": "..."},
                "owner/repo2": {"stars": 100, "description": "Desc 2", "language": "Go", "url": "..."},
                # repo3 is NOT in previous → new
            },
        }
        deltas = compute_star_deltas(current, previous)

        # Should be sorted by star_delta descending
        self.assertEqual(len(deltas), 3)

        # repo3 is new: star_delta = 8500 (highest, so should be first)
        self.assertEqual(deltas[0]["repo_name"], "owner/repo3")
        self.assertTrue(deltas[0]["is_new"])
        self.assertEqual(deltas[0]["star_delta"], 8500)

        # repo1: 5000 - 4500 = 500
        self.assertEqual(deltas[1]["repo_name"], "owner/repo1")
        self.assertFalse(deltas[1]["is_new"])
        self.assertEqual(deltas[1]["star_delta"], 500)

        # repo2: 200 - 100 = 100
        self.assertEqual(deltas[2]["repo_name"], "owner/repo2")
        self.assertFalse(deltas[2]["is_new"])
        self.assertEqual(deltas[2]["star_delta"], 100)

    def test_first_run_no_previous_snapshot(self):
        """When previous_snapshot is None, all repos are NEW."""
        current = [
            {
                "repo_name": "a/b",
                "stars": 300,
                "description": "X",
                "language": "Python",
                "html_url": "https://github.com/a/b",
                "topics": [],
                "created_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-05-01T00:00:00Z",
                "license": "MIT",
            },
            {
                "repo_name": "c/d",
                "stars": 100,
                "description": "Y",
                "language": "Go",
                "html_url": "https://github.com/c/d",
                "topics": [],
                "created_at": "2026-02-01T00:00:00Z",
                "pushed_at": "2026-05-02T00:00:00Z",
                "license": "Apache-2.0",
            },
        ]
        deltas = compute_star_deltas(current, None)

        self.assertEqual(len(deltas), 2)
        # Sorted descending by star_delta (which equals current.stars)
        self.assertEqual(deltas[0]["repo_name"], "a/b")
        self.assertTrue(deltas[0]["is_new"])
        self.assertEqual(deltas[0]["star_delta"], 300)

        self.assertEqual(deltas[1]["repo_name"], "c/d")
        self.assertTrue(deltas[1]["is_new"])
        self.assertEqual(deltas[1]["star_delta"], 100)

    def test_empty_previous_repos(self):
        """Empty repos dict in previous snapshot → all repos are NEW."""
        current = [
            {
                "repo_name": "x/y",
                "stars": 50,
                "description": "Z",
                "language": "Rust",
                "html_url": "https://github.com/x/y",
                "topics": [],
                "created_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-05-01T00:00:00Z",
                "license": "MIT",
            }
        ]
        previous = {"timestamp": "2026-01-01T00:00:00Z", "repos": {}}
        deltas = compute_star_deltas(current, previous)

        self.assertEqual(len(deltas), 1)
        self.assertTrue(deltas[0]["is_new"])
        self.assertEqual(deltas[0]["star_delta"], 50)

    def test_empty_current_repos(self):
        """Empty current_repos returns empty list."""
        deltas = compute_star_deltas([], {"timestamp": "x", "repos": {}})
        self.assertEqual(deltas, [])

    def test_empty_current_repos_no_snapshot(self):
        """Empty current_repos with None snapshot returns empty list."""
        deltas = compute_star_deltas([], None)
        self.assertEqual(deltas, [])

    def test_repo_removed_from_current(self):
        """A repo in previous but not in current is simply omitted from deltas."""
        current = [
            {
                "repo_name": "keep/me",
                "stars": 10,
                "description": "K",
                "language": "Python",
                "html_url": "https://github.com/keep/me",
                "topics": [],
                "created_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-05-01T00:00:00Z",
                "license": "MIT",
            }
        ]
        previous = {
            "timestamp": "x",
            "repos": {
                "keep/me": {"stars": 5, "description": "K", "language": "Python", "url": "..."},
                "gone/repo": {"stars": 999, "description": "G", "language": "Go", "url": "..."},
            },
        }
        deltas = compute_star_deltas(current, previous)
        self.assertEqual(len(deltas), 1)
        self.assertEqual(deltas[0]["repo_name"], "keep/me")
        self.assertFalse(deltas[0]["is_new"])
        self.assertEqual(deltas[0]["star_delta"], 5)


class TestGetTopN(unittest.TestCase):
    """Tests for get_top_n()."""

    def setUp(self):
        self.deltas = [
            {"repo_name": "a", "star_delta": 1000, "is_new": True, "stars": 1000, "description": "A"},
            {"repo_name": "b", "star_delta": 800, "is_new": False, "stars": 1200, "description": "B"},
            {"repo_name": "c", "star_delta": 500, "is_new": True, "stars": 500, "description": "C"},
            {"repo_name": "d", "star_delta": 300, "is_new": False, "stars": 900, "description": "D"},
            {"repo_name": "e", "star_delta": 100, "is_new": False, "stars": 400, "description": "E"},
        ]

    def test_top_3(self):
        """Returns top 3 by star_delta."""
        result = get_top_n(self.deltas, n=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["repo_name"], "a")
        self.assertEqual(result[1]["repo_name"], "b")
        self.assertEqual(result[2]["repo_name"], "c")

    def test_top_n_larger_than_list(self):
        """When n > len(deltas), returns all items."""
        result = get_top_n(self.deltas, n=10)
        self.assertEqual(len(result), 5)

    def test_n_zero(self):
        """n=0 returns empty list."""
        result = get_top_n(self.deltas, n=0)
        self.assertEqual(result, [])

    def test_empty_input(self):
        """Empty deltas returns empty list."""
        result = get_top_n([], n=10)
        self.assertEqual(result, [])

    def test_already_sorted_input(self):
        """Works correctly with already-sorted input."""
        already_sorted = [
            {"repo_name": "high", "star_delta": 900},
            {"repo_name": "med", "star_delta": 500},
            {"repo_name": "low", "star_delta": 100},
        ]
        result = get_top_n(already_sorted, n=2)
        self.assertEqual([r["repo_name"] for r in result], ["high", "med"])

    def test_unsorted_input(self):
        """Works correctly with unsorted input."""
        unsorted = [
            {"repo_name": "low", "star_delta": 100},
            {"repo_name": "high", "star_delta": 900},
            {"repo_name": "med", "star_delta": 500},
        ]
        result = get_top_n(unsorted, n=2)
        self.assertEqual([r["repo_name"] for r in result], ["high", "med"])


class TestBuildSnapshot(unittest.TestCase):
    """Tests for build_snapshot()."""

    def test_build_snapshot_format(self):
        """build_snapshot returns correctly structured dict."""
        current = [
            {
                "repo_name": "owner/repo1",
                "stars": 5000,
                "description": "A framework",
                "language": "Python",
                "html_url": "https://github.com/owner/repo1",
                "topics": ["ai"],
                "created_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-05-17T12:00:00Z",
                "license": "MIT",
            },
            {
                "repo_name": "owner/repo2",
                "stars": 200,
                "description": "A CLI tool",
                "language": "Go",
                "html_url": "https://github.com/owner/repo2",
                "topics": [],
                "created_at": "2026-02-01T00:00:00Z",
                "pushed_at": "2026-05-16T12:00:00Z",
                "license": "Apache-2.0",
            },
        ]
        snapshot = build_snapshot(current)

        # Top-level keys
        self.assertIn("timestamp", snapshot)
        self.assertIn("repos", snapshot)

        # Timestamp is ISO 8601 with Z
        ts = snapshot["timestamp"]
        self.assertTrue(ts.endswith("Z") or "+" in ts)
        # Should be parseable
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        # Should be within last minute (tolerance for test execution)
        now = datetime.now(timezone.utc)
        delta = abs((now - dt).total_seconds())
        self.assertLess(delta, 10, "Timestamp should be close to current UTC time")

        # repos dict
        repos = snapshot["repos"]
        self.assertIsInstance(repos, dict)
        self.assertEqual(len(repos), 2)

        # Repo 1
        self.assertIn("owner/repo1", repos)
        r1 = repos["owner/repo1"]
        self.assertEqual(r1["stars"], 5000)
        self.assertEqual(r1["description"], "A framework")
        self.assertEqual(r1["language"], "Python")
        self.assertEqual(r1["url"], "https://github.com/owner/repo1")

        # Repo 2
        self.assertIn("owner/repo2", repos)
        r2 = repos["owner/repo2"]
        self.assertEqual(r2["stars"], 200)
        self.assertEqual(r2["description"], "A CLI tool")
        self.assertEqual(r2["language"], "Go")
        self.assertEqual(r2["url"], "https://github.com/owner/repo2")

    def test_build_snapshot_empty(self):
        """build_snapshot with empty list returns empty repos dict."""
        snapshot = build_snapshot([])
        self.assertIn("timestamp", snapshot)
        self.assertEqual(snapshot["repos"], {})

    def test_repo_missing_optional_fields(self):
        """Handles repos with missing description/language gracefully."""
        current = [
            {
                "repo_name": "min/repo",
                "stars": 10,
                # no description
                # no language
                "html_url": "https://github.com/min/repo",
                "topics": [],
                "created_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-05-01T00:00:00Z",
                "license": None,
            }
        ]
        snapshot = build_snapshot(current)
        r = snapshot["repos"]["min/repo"]
        self.assertEqual(r["stars"], 10)
        self.assertEqual(r["description"], "")
        self.assertEqual(r["language"], "")
        self.assertEqual(r["url"], "https://github.com/min/repo")


if __name__ == "__main__":
    unittest.main()
