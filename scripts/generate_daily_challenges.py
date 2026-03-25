"""Generate daily challenge JSON files and upload them to S3.

Usage:
    python -m scripts.generate_daily_challenges [--start YYYY-MM-DD] [--days N]

Defaults: start = today (UTC), days = 90.
Each challenge is a comparison game with 10 questions using varied stats
and 'normal' difficulty. Files are uploaded to:
    s3://{bucket}/daily_challenges/YYYY-MM-DD.json

Re-running the script overwrites any previously generated challenges.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from core.aws import get_s3_client
from core.config import get_settings
from services.quiz import generate_comparison_set

S3_PREFIX = "daily_challenges"
NUM_QUESTIONS = 10
DIFFICULTY = "normal"


def generate_one_challenge(date: str) -> dict:
    """Generate a single daily challenge payload for a given date."""
    questions = generate_comparison_set(
        num_questions=NUM_QUESTIONS,
        difficulty=DIFFICULTY,
    )
    return {
        "date": date,
        "game_type": "comparison",
        "num_questions": len(questions),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "questions": questions,
    }


def upload_challenge(s3, bucket: str, date: str, payload: dict) -> None:
    """Upload a challenge JSON to S3."""
    key = f"{S3_PREFIX}/{date}.json"
    body = json.dumps(payload, ensure_ascii=False)
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType="application/json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily challenges and upload to S3")
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format (default: today UTC)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days to generate (default: 90)",
    )
    args = parser.parse_args()

    if args.start:
        try:
            start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"Error: invalid date format '{args.start}'. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        start_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    num_days = args.days
    settings = get_settings()
    s3 = get_s3_client()
    bucket = settings.s3_bucket_name

    print(f"Generating {num_days} daily challenges starting from {start_date.strftime('%Y-%m-%d')}")
    print(f"S3 bucket: {bucket}, prefix: {S3_PREFIX}/")

    for i in range(num_days):
        day = start_date + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        payload = generate_one_challenge(date_str)
        upload_challenge(s3, bucket, date_str, payload)
        print(f"  [{i + 1}/{num_days}] {date_str} — {payload['num_questions']} questions ✓")

    print(f"Done. {num_days} challenges uploaded to s3://{bucket}/{S3_PREFIX}/")


if __name__ == "__main__":
    main()
