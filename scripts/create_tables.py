#!/usr/bin/env python3
"""Create all GeoFreak DynamoDB tables.

Usage:
    python -m scripts.create_tables          # uses .env
    python -m scripts.create_tables --yes    # skip confirmation
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from core.config import get_settings
from core.aws import get_dynamodb_resource

settings = get_settings()
dynamodb = get_dynamodb_resource()

# ── Table definitions ────────────────────────────────────────────────────────
# Each entry: (short_name, key_schema, attribute_definitions, [gsi_list])

TABLE_DEFS: list[tuple] = [
    # 1. users
    (
        "users",
        [{"AttributeName": "user_id", "KeyType": "HASH"}],
        [{"AttributeName": "user_id", "AttributeType": "S"},
         {"AttributeName": "email", "AttributeType": "S"},
         {"AttributeName": "username", "AttributeType": "S"}],
        [
            {
                "IndexName": "email-index",
                "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "username-index",
                "KeySchema": [{"AttributeName": "username", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    ),
    # 2. user_stats
    (
        "user_stats",
        [{"AttributeName": "user_id", "KeyType": "HASH"}],
        [{"AttributeName": "user_id", "AttributeType": "S"}],
        [],
    ),
    # 3. matches
    (
        "matches",
        [{"AttributeName": "match_id", "KeyType": "HASH"}],
        [{"AttributeName": "match_id", "AttributeType": "S"}],
        [],
    ),
    # 4. match_players  (PK=match_id, SK=user_id)
    (
        "match_players",
        [
            {"AttributeName": "match_id", "KeyType": "HASH"},
            {"AttributeName": "user_id", "KeyType": "RANGE"},
        ],
        [
            {"AttributeName": "match_id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
        [],
    ),
    # 5. duels
    (
        "duels",
        [{"AttributeName": "duel_id", "KeyType": "HASH"}],
        [{"AttributeName": "duel_id", "AttributeType": "S"}],
        [],
    ),
    # 6. tournaments
    (
        "tournaments",
        [{"AttributeName": "tournament_id", "KeyType": "HASH"}],
        [{"AttributeName": "tournament_id", "AttributeType": "S"}],
        [],
    ),
    # 7. tournament_rounds  (PK=tournament_id, SK=round_id)
    (
        "tournament_rounds",
        [
            {"AttributeName": "tournament_id", "KeyType": "HASH"},
            {"AttributeName": "round_id", "KeyType": "RANGE"},
        ],
        [
            {"AttributeName": "tournament_id", "AttributeType": "S"},
            {"AttributeName": "round_id", "AttributeType": "S"},
        ],
        [],
    ),
    # 8. friendships  (PK=user_id, SK=friend_user_id)
    (
        "friendships",
        [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "friend_user_id", "KeyType": "RANGE"},
        ],
        [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "friend_user_id", "AttributeType": "S"},
        ],
        [],
    ),
    # 9. invites
    (
        "invites",
        [{"AttributeName": "invite_id", "KeyType": "HASH"}],
        [
            {"AttributeName": "invite_id", "AttributeType": "S"},
            {"AttributeName": "target_user_id", "AttributeType": "S"},
        ],
        [
            {
                "IndexName": "target-user-index",
                "KeySchema": [{"AttributeName": "target_user_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    ),
    # 10. leaderboards_cache
    (
        "leaderboards_cache",
        [
            {"AttributeName": "leaderboard_id", "KeyType": "HASH"},
        ],
        [
            {"AttributeName": "leaderboard_id", "AttributeType": "S"},
        ],
        [],
    ),
    # 11. analytics  (PK=pk, SK=sk)  — atomic counters
    (
        "analytics",
        [
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        [
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        [],
    ),
    # 12. ranked_attempts  (PK=test_key, SK=attempt_id)
    #     GSI: user-time-index (PK=user_id, SK=created_at)
    (
        "ranked_attempts",
        [
            {"AttributeName": "test_key", "KeyType": "HASH"},
            {"AttributeName": "attempt_id", "KeyType": "RANGE"},
        ],
        [
            {"AttributeName": "test_key", "AttributeType": "S"},
            {"AttributeName": "attempt_id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        [
            {
                "IndexName": "user-time-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    ),
    # 13. test_ratings  (PK=user_id, SK=test_key)
    (
        "test_ratings",
        [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "test_key", "KeyType": "RANGE"},
        ],
        [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "test_key", "AttributeType": "S"},
        ],
        [],
    ),
    # 14. records  (PK=config_key, SK=record_sort)
    (
        "records",
        [
            {"AttributeName": "config_key", "KeyType": "HASH"},
            {"AttributeName": "record_sort", "KeyType": "RANGE"},
        ],
        [
            {"AttributeName": "config_key", "AttributeType": "S"},
            {"AttributeName": "record_sort", "AttributeType": "S"},
        ],
        [],
    ),
]


def _table_exists(table_name: str) -> bool:
    """Check if a table exists using DescribeTable (no ListTables needed)."""
    try:
        table = dynamodb.Table(table_name)
        table.load()
        return True
    except Exception:
        return False


def create_tables(skip_existing: bool = True) -> None:
    for entry in TABLE_DEFS:
        short_name, key_schema, attr_defs, gsis = entry
        table_name = settings.table_name(short_name)

        if _table_exists(table_name):
            if skip_existing:
                print(f"  ⏭  {table_name} (already exists)")
                continue
            else:
                print(f"  🗑  Deleting {table_name} …")
                dynamodb.Table(table_name).delete()
                dynamodb.Table(table_name).wait_until_not_exists()

        print(f"  ✨ Creating {table_name} …")
        kwargs: dict = {
            "TableName": table_name,
            "KeySchema": key_schema,
            "AttributeDefinitions": attr_defs,
            "BillingMode": "PAY_PER_REQUEST",
        }
        if gsis:
            kwargs["GlobalSecondaryIndexes"] = gsis

        dynamodb.create_table(**kwargs)
        dynamodb.Table(table_name).wait_until_exists()
        print(f"  ✅ {table_name}")

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create GeoFreak DynamoDB tables")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    region = settings.aws_region
    endpoint = settings.dynamodb_endpoint_url or f"AWS ({region})"
    prefix = settings.dynamodb_table_prefix

    print(f"\n📦 DynamoDB target : {endpoint}")
    print(f"   Table prefix    : {prefix}")
    print(f"   Tables to create: {len(TABLE_DEFS)}\n")

    if not args.yes:
        confirm = input("Proceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            sys.exit(0)

    create_tables()
