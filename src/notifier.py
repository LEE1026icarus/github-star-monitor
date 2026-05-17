"""
Notifier module for GitHub Star Surge Monitor.

Formats Discord messages and sends them via webhook.
"""
import requests


def _format_number(n: int) -> str:
    """Format integer with comma separators: 4210 -> '4,210'."""
    return f"{n:,}"


def _extract_domain_path(html_url: str) -> str:
    """Extract 'github.com/owner/repo' from an html_url."""
    if not html_url:
        return ""
    # Remove protocol prefix
    result = html_url.replace("https://", "").replace("http://", "")
    # Remove trailing slash if present
    result = result.rstrip("/")
    return result


def format_discord_message(top_repos: list[dict], delta_hours: int = 12) -> str:
    """
    Format top repos into Discord-friendly markdown message.

    Args:
        top_repos: list of repo dicts sorted by star_delta desc.
                   Expected fields:
                     - repo_name (str)
                     - stars (int): current total stars
                     - star_delta (int): increase since last run
                     - description (str, optional)
                     - html_url (str, optional)
                     - is_new (bool, optional)
        delta_hours: hours between runs (displayed in header)

    Returns:
        Formatted string (max ~1900 chars for Discord 2000 char limit)
    """
    n = len(top_repos)
    lines = [f"🔥 GitHub 급상승 레포 Top {n}"]

    for i, repo in enumerate(top_repos, start=1):
        repo_name = repo.get("repo_name", "unknown/repo")
        stars = repo.get("stars", 0)
        star_delta = repo.get("star_delta", 0)
        description = repo.get("description", "")
        html_url = repo.get("html_url", "")
        is_new = repo.get("is_new", False)

        # Build the rank line
        if is_new:
            rank_line = f"{i}. 🆕 {repo_name}"
        else:
            rank_line = f"{i}. {repo_name}"

        # Stars line
        stars_line = f"   ⭐ +{_format_number(star_delta)} / {delta_hours}h · total {_format_number(stars)}"

        entry_lines = [rank_line, stars_line]

        # Description line (skip if empty or None)
        if description:
            desc_text = str(description)
            if len(desc_text) > 100:
                desc_text = desc_text[:100] + "..."
            entry_lines.append(f"   설명: {desc_text}")

        # Link line
        domain_path = _extract_domain_path(html_url)
        if domain_path:
            entry_lines.append(f"   링크: {domain_path}")

        lines.append("")
        lines.extend(entry_lines)

    message = "\n".join(lines)

    # If the message exceeds 1900 characters, truncate repos until it fits.
    # We do this by progressively removing repos from the end.
    if len(message) <= 1900:
        return message

    # Binary search approach: try fewer repos until we fit
    for try_n in range(n - 1, 0, -1):
        truncated_repos = top_repos[:try_n]
        candidate = format_discord_message(truncated_repos, delta_hours)
        if len(candidate) <= 1900:
            return candidate

    # Fallback: just the header
    return f"🔥 GitHub 급상승 레포 Top {len(top_repos)}"


def send_discord_notification(webhook_url: str, message: str) -> bool:
    """
    Send message to Discord webhook.

    Args:
        webhook_url: Discord webhook URL
        message: Formatted markdown message (max 2000 chars)

    Returns:
        True on success (HTTP 2xx), False on failure.
    """
    try:
        response = requests.post(
            webhook_url,
            json={"content": message},
            timeout=10,
        )
        return 200 <= response.status_code < 300
    except requests.RequestException:
        return False
