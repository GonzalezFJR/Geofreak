"""Avatar management — profile pictures stored in S3 under users/profile_pics/."""
import io
from datetime import datetime, timezone
from typing import Optional

from PIL import Image

from core.aws import get_s3_client
from core.config import get_settings

AVATAR_PREFIX = "users/profile_pics"
MAX_SIZE = 1024


def _avatar_key(email: str) -> str:
    return f"{AVATAR_PREFIX}/{email.lower()}.jpg"


def get_avatar_stream(email: str):
    """Return an S3 StreamingBody for the user's avatar, or None if not found."""
    s3 = get_s3_client()
    settings = get_settings()
    try:
        resp = s3.get_object(Bucket=settings.s3_bucket_name, Key=_avatar_key(email))
        return resp["Body"]
    except Exception:
        return None


def upload_avatar(email: str, image_bytes: bytes) -> None:
    """Upload avatar to S3. Archives the previous one with a timestamp suffix."""
    s3 = get_s3_client()
    settings = get_settings()
    bucket = settings.s3_bucket_name
    key = _avatar_key(email)

    # Archive existing avatar if present
    try:
        s3.head_object(Bucket=bucket, Key=key)
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        archive_key = f"{AVATAR_PREFIX}/{email.lower()}_{suffix}.jpg"
        s3.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": key},
            Key=archive_key,
        )
        s3.delete_object(Bucket=bucket, Key=key)
    except Exception:
        pass  # No existing avatar — nothing to archive

    # Decode, resize if needed, and re-encode as JPEG
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if img.width > MAX_SIZE or img.height > MAX_SIZE:
        img = img.resize((MAX_SIZE, MAX_SIZE), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    buf.seek(0)

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buf.read(),
        ContentType="image/jpeg",
    )
