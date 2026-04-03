"""Generate fake users with realistic names and correlated game scores.

Usage:
    python -m scripts.generate_fake_users [--count N] [--yes]

Creates N fake users (default 200) with:
  - Syllable-based random names (no external library needed)
  - is_fake=True flag on the user record
  - Correlated scores across game types (skill level determines accuracy range)
  - Ranked attempts and test ratings populated
  - Daily challenge scores populated
  - All rankings rebuilt afterwards
"""

import argparse
import math
import random
import sys
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from core.aws import get_dynamodb_resource
from core.config import get_settings

# ── Name generator ───────────────────────────────────────────────────────────

_ONSETS = [
    "", "b", "c", "d", "f", "g", "h", "j", "k", "l", "m", "n", "p", "r",
    "s", "t", "v", "w", "z", "br", "ch", "cl", "cr", "dr", "fl", "fr",
    "gl", "gr", "kr", "pl", "pr", "sh", "sk", "sl", "sm", "sn", "sp",
    "st", "str", "sw", "th", "tr", "tw", "wh",
]
_VOWELS = ["a", "e", "i", "o", "u", "ai", "ei", "ou", "au", "ea", "io"]
_CODAS = [
    "", "b", "c", "d", "f", "g", "k", "l", "m", "n", "p", "r", "s", "t",
    "x", "z", "ch", "ck", "ll", "nd", "ng", "nk", "nt", "rd", "rn",
    "rs", "rt", "sh", "sk", "st", "th",
]


def _gen_syllable() -> str:
    return random.choice(_ONSETS) + random.choice(_VOWELS) + random.choice(_CODAS)


def _gen_name(min_syl: int = 2, max_syl: int = 3) -> str:
    n_syl = random.randint(min_syl, max_syl)
    name = "".join(_gen_syllable() for _ in range(n_syl))
    return name.capitalize()


def generate_username() -> str:
    """Generate a unique-looking username."""
    base = _gen_name()
    suffix = random.choice([
        "", str(random.randint(1, 99)),
        "_" + _gen_name(1, 2).lower(),
        str(random.randint(100, 999)),
    ])
    return base + suffix


# ── Score generation ─────────────────────────────────────────────────────────

GAME_TYPES = ["flags", "outline", "comparison", "map-challenge", "relief-challenge", "ordering", "geostats"]
BINARY_GAMES = {"flags", "outline", "map-challenge", "relief-challenge", "comparison"}
SCORED_GAMES = {"geostats", "ordering"}

# tref defaults per game
TREF = {
    "flags": 20, "outline": 20, "comparison": 20,
    "map-challenge": 6, "relief-challenge": 8,
    "ordering": 20, "geostats": 20,
}


def generate_scores_for_user(skill: float, num_games: int = 5) -> list[dict]:
    """Generate multiple ranked attempts for a user based on skill level (0.1..0.95).

    skill determines the base quality q for the user, with per-attempt variance.
    All games share a correlated skill factor.
    """
    # Choose which game types this user plays (at least 2, up to all)
    n_types = max(2, min(len(GAME_TYPES), random.randint(2, num_games)))
    chosen = random.sample(GAME_TYPES, n_types)

    attempts = []
    for gt in chosen:
        # Per-game skill variation
        game_skill = max(0.05, min(0.98, skill + random.gauss(0, 0.08)))
        num_q = random.choice([10, 15, 20, 25, 30])
        n_attempts = random.randint(3, 12)

        for _ in range(n_attempts):
            # Per-attempt variance
            q = max(0.01, min(0.99, game_skill + random.gauss(0, 0.06)))

            # Time: better players tend to be faster
            tref = TREF.get(gt, 20)
            base_tpp = tref * (1.2 - 0.5 * q + random.gauss(0, 0.15))
            base_tpp = max(tref * 0.3, base_tpp)
            time_seconds = base_tpp * num_q

            # Score
            if gt in BINARY_GAMES:
                correct = max(0, min(num_q, round(q * num_q)))
                total = num_q
                per_question_scores = None
            else:
                per_question_scores = [max(0, min(10, round(q * 10 + random.gauss(0, 1.5), 1))) for _ in range(num_q)]
                correct = sum(per_question_scores)
                total = num_q * 10

            # Compute S
            Q = q ** 3
            tpp = time_seconds / num_q
            T = 1.0 / (1.0 + 0.35 * (tpp / tref))
            C = 1.0 - math.exp(-num_q / 15.0)
            score_s = 1000.0 * Q * T * C

            attempts.append({
                "game_type": gt,
                "q": q,
                "score_s": score_s,
                "num_questions": num_q,
                "time_seconds": time_seconds,
                "tpp": tpp,
                "tref": tref,
                "correct": correct,
                "total": total,
                "per_question_scores": per_question_scores,
            })

    return attempts


# ── DynamoDB operations ──────────────────────────────────────────────────────

def create_fake_user(username: str, settings) -> dict:
    """Create a user record with is_fake=True."""
    now = datetime.now(timezone.utc)
    # Randomize creation date (last 3 months)
    days_ago = random.randint(1, 90)
    created_at = (now - timedelta(days=days_ago)).isoformat()

    user_id = str(uuid.uuid4())
    email = f"{username.lower()}@fake.geofreak.test"
    lang = random.choice(["es", "en", "fr", "it", "ru"])

    item = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "password_hash": "FAKE_NO_LOGIN",
        "created_at": created_at,
        "updated_at": now.isoformat(),
        "plan": "free",
        "role": "free",
        "status": "active",
        "country": random.choice(["ES", "US", "FR", "IT", "RU", "DE", "MX", "AR", "BR", "GB"]),
        "language": lang,
        "settings": {},
        "is_fake": True,
    }

    table = get_dynamodb_resource().Table(settings.table_name("users"))
    table.put_item(Item=item)
    return item


def store_attempts(user_id: str, username: str, attempts: list[dict], settings):
    """Store ranked attempts and update test ratings for a fake user."""
    from services.scoring import (
        build_test_key,
        get_week_key,
        get_day_key,
        compute_percentile,
    )

    attempts_table = get_dynamodb_resource().Table(settings.table_name("ranked_attempts"))
    ratings_table = get_dynamodb_resource().Table(settings.table_name("test_ratings"))

    now = datetime.now(timezone.utc)
    # Spread attempts over the last 8 weeks
    ratings_by_test: dict[str, list[float]] = {}

    for i, att in enumerate(attempts):
        # Random time in the past
        days_ago = random.randint(0, 56)
        att_time = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))

        config = {"dataset": "countries", "continent": "all"}
        if att["game_type"] in ("map-challenge", "relief-challenge"):
            config["category"] = "all"

        test_key = build_test_key(att["game_type"], config, att["num_questions"])
        attempt_id = str(uuid.uuid4())
        week_key = get_week_key(att_time)
        day_key = get_day_key(att_time)

        item = {
            "test_key": test_key,
            "attempt_id": attempt_id,
            "user_id": user_id,
            "game_type": att["game_type"],
            "q": Decimal(str(round(att["q"], 6))),
            "score_s": Decimal(str(round(att["score_s"], 4))),
            "n": att["num_questions"],
            "time_seconds": Decimal(str(round(att["time_seconds"], 2))),
            "tpp": Decimal(str(round(att["tpp"], 4))),
            "tref": Decimal(str(round(att["tref"], 2))),
            "week_key": week_key,
            "day_key": day_key,
            "created_at": att_time.isoformat(),
        }
        attempts_table.put_item(Item=item)

        # Collect for rating computation
        if test_key not in ratings_by_test:
            ratings_by_test[test_key] = []
        ratings_by_test[test_key].append(att["score_s"])

    # Compute and store test ratings (using average score_s as percentile proxy)
    for test_key, scores in ratings_by_test.items():
        avg_s = sum(scores) / len(scores)
        # Map score_s to a pseudo-percentile (0..100)
        percentile = min(99.0, max(1.0, avg_s / 10.0))
        # Simple EMA-like rating
        rating = percentile
        for s in scores[1:]:
            p = min(99.0, max(1.0, s / 10.0))
            rating = 0.80 * rating + 0.20 * p

        game_type = test_key.split(":")[0]
        ratings_table.put_item(Item={
            "user_id": user_id,
            "test_key": test_key,
            "game_type": game_type,
            "rating": Decimal(str(round(rating, 4))),
            "best_daily_percentile": Decimal(str(round(max(min(99, s / 10) for s in scores), 4))),
            "attempts_count": len(scores),
            "updated_at": now.isoformat(),
        })


def store_daily_scores(user_id: str, username: str, skill: float, settings):
    """Generate and store daily challenge scores for a fake user."""
    daily_table = get_dynamodb_resource().Table(settings.table_name("daily_scores"))
    now = datetime.now(timezone.utc)

    # Random number of daily challenges (5..40 days)
    num_days = random.randint(5, 40)
    days = random.sample(range(0, 90), min(num_days, 90))

    for d in days:
        day_dt = now - timedelta(days=d)
        date_str = day_dt.strftime("%Y-%m-%d")

        q = max(0.01, min(0.99, skill + random.gauss(0, 0.08)))
        Q = q ** 3
        tref = 20.0
        tpp = tref * (1.2 - 0.5 * q + random.gauss(0, 0.15))
        tpp = max(tref * 0.3, tpp)
        T = 1.0 / (1.0 + 0.35 * tpp / tref)
        n = random.choice([10, 15, 20])
        C = 1.0 - math.exp(-n / 15.0)
        score_s = 1000.0 * Q * T * C

        daily_table.put_item(Item={
            "user_id": user_id,
            "date": date_str,
            "username": username,
            "score_s": Decimal(str(round(score_s, 4))),
            "q": Decimal(str(round(q, 6))),
            "n": n,
            "time_seconds": Decimal(str(round(tpp * n, 2))),
            "game_type": random.choice(["flags", "outline", "comparison"]),
            "created_at": day_dt.isoformat(),
        })


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate fake users with scores")
    parser.add_argument("--count", "-n", type=int, default=200, help="Number of fake users")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if not args.yes:
        confirm = input(f"Create {args.count} fake users? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            sys.exit(0)

    settings = get_settings()
    used_names: set[str] = set()

    print(f"Creating {args.count} fake users...")
    for i in range(args.count):
        # Generate unique username
        while True:
            username = generate_username()
            if username not in used_names and len(username) >= 4:
                used_names.add(username)
                break

        # Skill level: roughly normal distribution centered at 0.5
        skill = max(0.10, min(0.90, random.gauss(0.50, 0.18)))

        # Create user
        user = create_fake_user(username, settings)
        uid = user["user_id"]

        # Generate and store game attempts
        attempts = generate_scores_for_user(skill)
        store_attempts(uid, username, attempts, settings)

        # Generate daily scores
        store_daily_scores(uid, username, skill, settings)

        if (i + 1) % 20 == 0:
            print(f"  ... {i + 1}/{args.count}")

    print(f"Created {args.count} fake users.")
    print("Rebuilding rankings...")

    from services.rankings import rebuild_all_rankings
    from services.daily_rankings import rebuild_all_daily_rankings

    r1 = rebuild_all_rankings()
    r2 = rebuild_all_daily_rankings()
    print(f"Rankings rebuilt: {r1}")
    print(f"Daily rankings rebuilt: {r2}")
    print("Done!")


if __name__ == "__main__":
    main()
