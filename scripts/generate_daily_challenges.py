"""Generate daily challenge JSON files and upload them to S3.

Usage:
    python -m scripts.generate_daily_challenges [options]

Options:
    --game          comparison|ordering|geostats (default: comparison)
    --start         Start date YYYY-MM-DD (default: today UTC)
    --days          Number of days (default: 90)
    --dates         Comma-separated specific dates YYYY-MM-DD (overrides --start/--days)
    --difficulty    easy|normal|hard|very_hard|extreme (default: normal)
    --num-questions N (default: 10)
    --secs-per-item N (default: 15)
    --no-countdown  Disable countdown timer (default: enabled)
    --no-overwrite  Skip dates that already exist in S3

Files are uploaded to:
    s3://{bucket}/daily_challenges/YYYY-MM-DD.json
    s3://{bucket}/daily_challenges/_index.json  (metadata index)
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from core.aws import get_s3_client
from core.config import get_settings
from services.quiz import generate_comparison_set, generate_ordering_set, generate_geostats_set

S3_PREFIX = "daily_challenges"
S3_INDEX_KEY = f"{S3_PREFIX}/_index.json"
VALID_DIFFICULTIES = ("easy", "normal", "hard", "very_hard", "extreme")
VALID_GAMES = ("comparison", "ordering", "geostats")


def _load_s3_index(s3, bucket: str) -> dict:
    """Load the _index.json from S3, returns {} on error."""
    try:
        resp = s3.get_object(Bucket=bucket, Key=S3_INDEX_KEY)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except Exception:
        return {}


def _save_s3_index(s3, bucket: str, index: dict) -> None:
    """Save the _index.json to S3."""
    body = json.dumps(index, ensure_ascii=False, sort_keys=True)
    s3.put_object(
        Bucket=bucket, Key=S3_INDEX_KEY,
        Body=body.encode("utf-8"), ContentType="application/json",
    )


def _date_exists_in_s3(s3, bucket: str, date: str) -> bool:
    """Return True if a challenge already exists in S3 for the given date."""
    key = f"{S3_PREFIX}/{date}.json"
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def generate_one_challenge(
    date: str,
    game: str,
    difficulty: str,
    num_questions: int,
    secs_per_item: int,
    countdown: bool,
) -> dict:
    """Generate a single daily challenge payload for a given date and game type."""
    base = {
        "date": date,
        "game_type": game,
        "difficulty": difficulty,
        "secs_per_item": secs_per_item,
        "countdown": countdown,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if game == "comparison":
        questions = generate_comparison_set(num_questions=num_questions, difficulty=difficulty)
        base["questions"] = questions
        base["num_questions"] = len(questions)
    elif game == "ordering":
        questions = generate_ordering_set(num_questions=num_questions, difficulty=difficulty)
        base["questions"] = questions
        base["num_questions"] = len(questions)
    elif game == "geostats":
        result = generate_geostats_set(num_questions=num_questions)
        base["questions"] = result["questions"]
        base["countries_lookup"] = result["countries_lookup"]
        base["max_attempts"] = result["max_attempts"]
        base["num_questions"] = len(result["questions"])

    return base


def upload_challenge(s3, bucket: str, date: str, payload: dict) -> None:
    """Upload a challenge JSON to S3."""
    key = f"{S3_PREFIX}/{date}.json"
    body = json.dumps(payload, ensure_ascii=False)
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType="application/json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily challenges and upload to S3")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--days", type=int, default=90, help="Number of days to generate (default: 90)")
    parser.add_argument("--dates", type=str, default=None, help="Comma-separated specific dates YYYY-MM-DD")
    parser.add_argument("--game", type=str, default="comparison", choices=VALID_GAMES, help="Game type")
    parser.add_argument("--difficulty", type=str, default="normal", choices=VALID_DIFFICULTIES, help="Difficulty level")
    parser.add_argument("--num-questions", type=int, default=10, dest="num_questions", help="Questions per challenge (default: 10)")
    parser.add_argument("--secs-per-item", type=int, default=15, dest="secs_per_item", help="Seconds per item for countdown (default: 15)")
    parser.add_argument("--no-countdown", action="store_true", dest="no_countdown", help="Disable countdown timer")
    parser.add_argument("--no-overwrite", action="store_true", dest="no_overwrite", help="Skip dates already in S3")
    args = parser.parse_args()

    # Build list of dates
    if args.dates:
        date_list = [d.strip() for d in args.dates.split(",") if d.strip()]
        for d in date_list:
            try:
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                print(f"Error: invalid date '{d}'. Use YYYY-MM-DD.")
                sys.exit(1)
    else:
        if args.start:
            try:
                start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                print(f"Error: invalid date '{args.start}'. Use YYYY-MM-DD.")
                sys.exit(1)
        else:
            start_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        date_list = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(args.days)]

    countdown = not args.no_countdown
    settings = get_settings()
    s3 = get_s3_client()
    bucket = settings.s3_bucket_name

    print(f"Game: {args.game} | Difficulty: {args.difficulty} | Questions: {args.num_questions} | Countdown: {countdown}")
    print(f"Dates: {len(date_list)} | No-overwrite: {args.no_overwrite}")
    print(f"S3: s3://{bucket}/{S3_PREFIX}/")

    index = _load_s3_index(s3, bucket)

    generated = 0
    skipped = 0
    for i, date_str in enumerate(date_list, 1):
        if args.no_overwrite and _date_exists_in_s3(s3, bucket, date_str):
            print(f"  [{i}/{len(date_list)}] {date_str} — SKIP (already exists)")
            skipped += 1
            continue

        payload = generate_one_challenge(
            date_str,
            game=args.game,
            difficulty=args.difficulty,
            num_questions=args.num_questions,
            secs_per_item=args.secs_per_item,
            countdown=countdown,
        )
        upload_challenge(s3, bucket, date_str, payload)
        index[date_str] = {
            "game_type": args.game,
            "difficulty": args.difficulty,
            "num_questions": payload["num_questions"],
        }
        print(f"  [{i}/{len(date_list)}] {date_str} — {payload['num_questions']} questions ({args.game}) ✓")
        generated += 1

    _save_s3_index(s3, bucket, index)
    print(f"Done. Generated: {generated}, Skipped: {skipped}. Index updated.")


if __name__ == "__main__":
    main()
