#!/usr/bin/env python3
"""
GitHub Star Surge Monitor — Main Entry Point

12시간마다 OSS Insight + GitHub API로 스타 급증 레포 Top 10을 탐지하여
Discord 알림을 보내고 결과를 ai-team-results 레포에 저장합니다.

Usage:
    python scripts/monitor.py
    python scripts/monitor.py --dry-run    # Discord 전송 없이 출력만
    python scripts/monitor.py --no-push    # git push 없이 로컬 저장만

Environment variables (.env):
    GITHUB_TOKEN         — GitHub Personal Access Token
    DISCORD_WEBHOOK_URL  — Discord Webhook URL
    RESULTS_REPO_PATH    — ai-team-results 로컬 클론 경로
    OSS_INSIGHT_BASE_URL — OSS Insight API base URL (optional)
    TRENDING_LIMIT       — 조회할 trending repo 수 (default: 30)
    TOP_N                — 알림 보낼 Top N (default: 10)
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from src.fetcher import fetch_trending_repos, enrich_trending_repos
from src.comparator import (
    load_snapshot,
    save_snapshot,
    compute_star_deltas,
    get_top_n,
    build_snapshot,
)
from src.notifier import format_discord_message, send_discord_notification

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("monitor")

# ---------------------------------------------------------------------------
# Paths & defaults
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
SNAPSHOT_PATH = os.path.join(DATA_DIR, "snapshot.json")
DEFAULT_RESULTS_REPO = os.path.expanduser("~/ai_team/workspace/ai-team-results")
DELTA_HOURS = 12


def load_config() -> dict:
    """Load configuration from .env file or environment variables."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        logger.warning(".env file not found at %s. Falling back to environment variables.", env_path)

    github_token = os.getenv("GITHUB_TOKEN")
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")

    if not github_token:
        logger.error("GITHUB_TOKEN not set in .env")
        sys.exit(1)
    if not discord_webhook:
        logger.error("DISCORD_WEBHOOK_URL not set in .env")
        sys.exit(1)

    return {
        "github_token": github_token,
        "discord_webhook": discord_webhook,
        "results_repo_path": os.path.expanduser(
            os.getenv("RESULTS_REPO_PATH", DEFAULT_RESULTS_REPO)
        ),
        "trending_limit": int(os.getenv("TRENDING_LIMIT", "30")),
        "top_n": int(os.getenv("TOP_N", "10")),
    }


def save_results_markdown(top_repos: list[dict], results_dir: str) -> str:
    """Save results as markdown file and return the file path."""
    os.makedirs(results_dir, exist_ok=True)

    now = datetime.now(timezone.utc)
    # Use KST for filename readability
    kst_now = now.astimezone().replace(tzinfo=None)  # simplified
    # Actually let's just use UTC for consistency
    timestamp = now.strftime("%Y-%m-%d_%H%M")
    filename = f"{timestamp}.md"
    filepath = os.path.join(results_dir, filename)

    lines = [
        f"# 🔥 GitHub 급상승 레포 Top {len(top_repos)}",
        "",
        f"**기준:** {DELTA_HOURS}시간 스타 증가량",
        f"**집계 시각:** {now.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
        "| # | Repository | ⭐ +delta | Total Stars | Language | Description |",
        "|---|------------|----------|-------------|----------|-------------|",
    ]

    for i, repo in enumerate(top_repos, start=1):
        name = repo.get("repo_name", "unknown")
        star_delta = repo.get("star_delta", 0)
        stars = repo.get("stars", 0)
        language = repo.get("language", "") or ""
        desc = (repo.get("description") or "")[:80]
        url = repo.get("html_url", "")
        is_new = "🆕" if repo.get("is_new") else ""

        name_cell = f"[{name}]({url}) {is_new}" if url else f"{name} {is_new}"
        lines.append(
            f"| {i} | {name_cell} | +{star_delta:,} | {stars:,} | {language} | {desc} |"
        )

    lines.extend([
        "",
        "---",
        f"*자동 생성: GitHub Star Surge Monitor*",
    ])

    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Results saved to %s", filepath)
    return filepath


def push_to_github(results_repo_path: str, results_dir: str) -> bool:
    """Commit and push results to the ai-team-results GitHub repo."""
    if not os.path.isdir(os.path.join(results_repo_path, ".git")):
        logger.warning("Not a git repository: %s. Skipping push.", results_repo_path)
        return False

    try:
        # git add
        subprocess.run(
            ["git", "add", "results/github-star-monitor/"],
            cwd=results_repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # Check if there are changes
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=results_repo_path,
            capture_output=True,
        )
        if diff_result.returncode == 0:
            logger.info("No changes to commit.")
            return True

        # git commit
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        subprocess.run(
            ["git", "commit", "-m", f"📊 GitHub Star Surge Report — {now}"],
            cwd=results_repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # git pull --rebase (to avoid conflicts)
        subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=results_repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # git push
        subprocess.run(
            ["git", "push"],
            cwd=results_repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        logger.info("Results pushed to GitHub successfully.")
        return True

    except subprocess.CalledProcessError as e:
        logger.error("Git operation failed: %s", e.stderr if hasattr(e, "stderr") else str(e))
        return False


def main():
    parser = argparse.ArgumentParser(description="GitHub Star Surge Monitor")
    parser.add_argument("--dry-run", action="store_true", help="Print Discord message without sending")
    parser.add_argument("--no-push", action="store_true", help="Skip git push")
    args = parser.parse_args()

    # --- Load config ---
    config = load_config()
    logger.info("Config loaded. Trending limit=%d, Top N=%d", config["trending_limit"], config["top_n"])

    # --- Step 1: Fetch trending repos from OSS Insight ---
    logger.info("Fetching trending repos from OSS Insight...")
    trending = fetch_trending_repos(period="past_24_hours", limit=config["trending_limit"])
    logger.info("Got %d trending repos.", len(trending))

    if not trending:
        logger.warning("No trending repos found. Exiting.")
        return

    # --- Step 2: Enrich with GitHub API ---
    logger.info("Enriching repos with GitHub API details...")
    enriched = enrich_trending_repos(trending, config["github_token"])
    logger.info("Enriched %d repos.", len(enriched))

    if not enriched:
        logger.warning("All repos failed to enrich. Exiting.")
        return

    # --- Step 3: Load previous snapshot & compute deltas ---
    previous = load_snapshot(SNAPSHOT_PATH)
    if previous:
        logger.info("Loaded previous snapshot from %s", previous.get("timestamp", "unknown"))
    else:
        logger.info("No previous snapshot found (first run).")

    deltas = compute_star_deltas(enriched, previous)
    top_repos = get_top_n(deltas, config["top_n"])
    logger.info("Top %d repos by star delta computed.", len(top_repos))

    # --- Step 4: Format & send Discord notification ---
    message = format_discord_message(top_repos, delta_hours=DELTA_HOURS)
    logger.info("Discord message length: %d chars", len(message))

    if args.dry_run:
        print("=" * 60)
        print("DRY RUN — Discord message:")
        print("=" * 60)
        print(message)
        print("=" * 60)
    else:
        success = send_discord_notification(config["discord_webhook"], message)
        if success:
            logger.info("Discord notification sent successfully.")
        else:
            logger.error("Failed to send Discord notification.")

    # --- Step 5: Save results markdown ---
    results_dir = os.path.join(config["results_repo_path"], "results", "github-star-monitor")
    filepath = save_results_markdown(top_repos, results_dir)

    # --- Step 6: Build & save snapshot for next run ---
    new_snapshot = build_snapshot(enriched)
    save_snapshot(new_snapshot, SNAPSHOT_PATH)
    logger.info("New snapshot saved for next run.")

    # --- Step 7: Push to GitHub ---
    if not args.no_push:
        push_to_github(config["results_repo_path"], results_dir)
    else:
        logger.info("Skipping git push (--no-push).")

    logger.info("Monitor run complete.")


if __name__ == "__main__":
    main()
