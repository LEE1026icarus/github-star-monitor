"""Star delta computation and snapshot management for GitHub Star Surge Monitor.

Compares current enriched repos with a previous snapshot to compute
star deltas and rankings.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any


def load_snapshot(path: str) -> dict | None:
    """Load previous snapshot from JSON file.

    Returns the parsed dict, or None if the file doesn't exist or can't
    be read/parsed.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def save_snapshot(data: dict, path: str) -> None:
    """Save current snapshot to JSON file.

    Creates parent directories if they don't exist.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def compute_star_deltas(
    current_repos: list[dict], previous_snapshot: dict | None
) -> list[dict]:
    """Compare current repos with previous snapshot to compute star deltas.

    For each repo in *current_repos*:
      - ``star_delta`` = current.stars - previous_snapshot.repos[name].stars
        (if the repo existed in the previous snapshot).  Otherwise
        ``star_delta`` = current.stars and the repo is flagged as new.
      - ``is_new`` = True only when the repo was **not** present in the
        previous snapshot.

    The returned list is sorted by ``star_delta`` descending.

    Parameters
    ----------
    current_repos : list[dict]
        Enriched repo dicts as returned by the fetcher module.  Each dict
        must contain at least ``"repo_name"`` and ``"stars"``.
    previous_snapshot : dict | None
        A snapshot dict as produced by :func:`build_snapshot`, or ``None``
        for a first run.

    Returns
    -------
    list[dict]
        Each item is a dict with the original repo fields plus
        ``"star_delta"`` (int) and ``"is_new"`` (bool), sorted by
        ``star_delta`` descending.
    """
    if previous_snapshot is None:
        prev_repos: dict[str, dict] = {}
    else:
        prev_repos = previous_snapshot.get("repos", {})

    results: list[dict] = []
    for repo in current_repos:
        name = repo.get("repo_name", "")
        if not name:
            continue

        prev = prev_repos.get(name)

        if prev is not None:
            star_delta = repo.get("stars", 0) - prev.get("stars", 0)
            is_new = False
        else:
            star_delta = repo.get("stars", 0)
            is_new = True

        entry: dict[str, Any] = dict(repo)
        entry["star_delta"] = star_delta
        entry["is_new"] = is_new
        results.append(entry)

    results.sort(key=lambda r: r["star_delta"], reverse=True)
    return results


def get_top_n(deltas: list[dict], n: int = 10) -> list[dict]:
    """Return the top *N* repos by ``star_delta``.

    The input list is assumed to already be sorted by ``star_delta``
    descending (as returned by :func:`compute_star_deltas`), but this
    function re-sorts defensively to guarantee correct output even with
    unsorted input.

    Parameters
    ----------
    deltas : list[dict]
        List of repo delta dicts.
    n : int
        Number of items to return (default 10).

    Returns
    -------
    list[dict]
        Up to *n* items sorted by ``star_delta`` descending.
    """
    if n <= 0:
        return []
    sorted_deltas = sorted(deltas, key=lambda r: r.get("star_delta", 0), reverse=True)
    return sorted_deltas[:n]


def build_snapshot(current_repos: list[dict]) -> dict:
    """Build a snapshot dict from the current repo list for the next run.

    The snapshot format is::

        {
            "timestamp": "<ISO 8601 UTC>",
            "repos": {
                "owner/repo": {
                    "stars": <int>,
                    "description": "<str>",
                    "language": "<str>",
                    "url": "<str>"
                },
                ...
            }
        }

    Parameters
    ----------
    current_repos : list[dict]
        Enriched repo dicts from the fetcher.

    Returns
    -------
    dict
        Snapshot suitable for saving to disk and feeding into
        :func:`compute_star_deltas` on the next run.
    """
    repos: dict[str, dict] = {}
    for repo in current_repos:
        name = repo.get("repo_name", "")
        if not name:
            continue
        repos[name] = {
            "stars": repo.get("stars", 0),
            "description": repo.get("description", ""),
            "language": repo.get("language", ""),
            "url": repo.get("html_url", ""),
        }

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"timestamp": timestamp, "repos": repos}
