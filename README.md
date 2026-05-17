# GitHub Star Surge Monitor 🚀

12시간마다 GitHub에서 스타가 급증한 레포지토리 Top 10을 자동 탐지하여 Discord로 알려주는 파이프라인.

## How It Works

```
GitHub Actions cron (2x/day)
  → OSS Insight Trending API (past_24_hours)
    → GitHub API (stargazers_count 상세)
      → snapshot.json 비교 (star_delta 계산)
        → Top 10 추출
          → Discord Webhook 알림 🔥
          → ai-team-results 레포에 결과 저장
```

## Setup

```bash
cp .env.example .env
# .env 파일에 DISCORD_WEBHOOK_URL, GITHUB_TOKEN 설정
pip install -r requirements.txt
```

## Run

```bash
# Dry-run (알림/푸시 생략)
DRY_RUN=true python scripts/monitor.py

# 실제 실행
python scripts/monitor.py
```

## Cron

GitHub Actions에서 1일 2회 자동 실행 (KST 09:00 / 21:00)
