"""
GitHub Star Surge Monitor — fetcher module.

Fetches trending repositories from the OSS Insight API and enriches them
with detailed metadata from the GitHub REST API v3.
"""

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OSS_INSIGHT_TRENDS_URL = "https://api.ossinsight.io/v1/trends/repos/"
GITHUB_API_URL = "https://api.github.com/repos"

USER_AGENT = "github-star-monitor/1.0"

# Keys we extract from the OSS Insight rows
_OSS_KEYS = ["repo_name", "stars", "description", "primary_language"]

# Keys we extract from the GitHub API response
_GITHUB_KEYS = {
    "full_name": "full_name",
    "stargazers_count": "stargazers_count",
    "description": "description",
    "language": "language",
    "html_url": "html_url",
    "topics": "topics",
    "created_at": "created_at",
    "pushed_at": "pushed_at",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_trending_repos(period: str = "past_24_hours", limit: int = 30) -> list[dict]:
    """
    Fetch trending repositories from the OSS Insight API.

    Args:
        period: Time window (e.g. 'past_24_hours', 'past_7_days').
        limit: Maximum number of repositories to return.

    Returns:
        List of dicts with keys: repo_name, stars, description, primary_language.
        Returns an empty list on any error.
    """
    params: dict[str, str | int] = {"period": period}
    try:
        resp = requests.get(OSS_INSIGHT_TRENDS_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OSS Insight API request failed: %s", exc)
        return []

    # OSS Insight wraps the actual data inside a "data" key:
    #   {"type": "sql_endpoint", "data": {"columns": [...], "rows": [...]}}
    inner = data.get("data", data)
    rows = inner.get("rows", [])
    if not isinstance(rows, list):
        logger.warning("Unexpected OSS Insight response format: rows is not a list")
        return []

    results: list[dict] = []
    for row in rows[:limit]:
        record: dict[str, Any] = {}
        for key in _OSS_KEYS:
            record[key] = row.get(key)
        # Convert numeric strings to int (OSS Insight returns strings)
        if "stars" in record and isinstance(record["stars"], str):
            try:
                record["stars"] = int(record["stars"])
            except (ValueError, TypeError):
                record["stars"] = 0
        results.append(record)

    return results


def fetch_repo_details(owner: str, repo: str, github_token: str) -> dict | None:
    """
    Fetch detailed repository information from the GitHub REST API v3.

    Args:
        owner: GitHub repository owner (user or organisation).
        repo: Repository name.
        github_token: GitHub personal access token for authentication.

    Returns:
        Dict with keys: full_name, stargazers_count, description, language,
        html_url, topics, created_at, pushed_at, license (spdx_id string or None).
        Returns None if the request fails or the repository is not found.
    """
    url = f"{GITHUB_API_URL}/{owner}/{repo}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("GitHub API request failed for %s/%s: %s", owner, repo, exc)
        return None

    license_info = data.get("license")
    license_spdx: str | None = license_info.get("spdx_id") if license_info else None

    details: dict[str, Any] = {
        "full_name": data.get("full_name"),
        "stargazers_count": data.get("stargazers_count"),
        "description": data.get("description"),
        "language": data.get("language"),
        "html_url": data.get("html_url"),
        "topics": data.get("topics", []),
        "created_at": data.get("created_at"),
        "pushed_at": data.get("pushed_at"),
        "license": license_spdx,
    }

    return details


def enrich_trending_repos(trending: list[dict], github_token: str) -> list[dict]:
    """
    Enrich OSS Insight trending data with accurate GitHub API details.

    For each trending repository the GitHub API is queried to obtain the
    canonical ``stargazers_count`` and additional metadata (topics, licence, …).

    Args:
        trending: List of dicts as returned by :func:`fetch_trending_repos`.
        github_token: GitHub personal access token.

    Returns:
        Enriched list with keys: repo_name, stars, description, language,
        html_url, topics, created_at, pushed_at, license.
        Repositories whose GitHub API call fails are silently skipped.
    """
    enriched: list[dict] = []

    for repo in trending:
        full_name = repo.get("repo_name", "")
        if not full_name or "/" not in full_name:
            logger.warning("Skipping repo with invalid repo_name: %r", full_name)
            continue

        owner, _, repo_name = full_name.partition("/")

        try:
            details = fetch_repo_details(owner, repo_name, github_token)
        except Exception as exc:
            logger.warning("Exception enriching %s: %s", full_name, exc)
            continue

        if details is None:
            logger.info("Skipping %s — GitHub API returned no data", full_name)
            continue

        enriched.append({
            "repo_name": full_name,
            "stars": details.get("stargazers_count", repo.get("stars")),
            "description": details.get("description", repo.get("description")),
            "language": details.get("language", repo.get("primary_language")),
            "html_url": details.get("html_url"),
            "topics": details.get("topics", []),
            "created_at": details.get("created_at"),
            "pushed_at": details.get("pushed_at"),
            "license": details.get("license"),
        })

    return enriched
