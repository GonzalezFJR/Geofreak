"""Centralised application settings loaded from environment variables."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All env-driven configuration lives here."""

    # App
    app_name: str = "GeoFreak"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    # Security
    secret_key: str = "geofreak-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Admin
    admin_user: str = ""
    admin_pass: str = ""

    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "eu-west-1"

    # DynamoDB
    dynamodb_table_prefix: str = "geofreak_"
    dynamodb_endpoint_url: Optional[str] = None

    # S3
    s3_bucket_name: str = "geofreak-assets"
    s3_endpoint_url: Optional[str] = None

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "GeoFreak"
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    mail_to: str = ""

    # Public URL (for email links)
    base_url: str = "https://geofreak.net"

    # Docker (read from .env but only used by docker-compose)
    docker_container_name: str = "geofreak-app"
    docker_image_name: str = "geofreak"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # ── helpers ──────────────────────────────────────────

    def table_name(self, short_name: str) -> str:
        """Return the full DynamoDB table name with prefix."""
        return f"{self.dynamodb_table_prefix}{short_name}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
