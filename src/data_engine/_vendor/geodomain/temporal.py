"""Temporal kinds and strict UTC ISO-8601 validation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any

from pydantic import BeforeValidator


class TemporalKind(str, Enum):
    """Semantic role of a timestamp in the domain."""

    ACQUIRED_AT = "acquired_at"  # Exact sensor/satellite image capture UTC time
    OBSERVED_AT = "observed_at"  # Agronomic occurrence time in the physical field
    PUBLISHED_at = "published_at"  # Document or research source release date
    INGESTED_AT = "ingested_at"  # Storage and SHA-256 ingestion timestamp
    CREATED_AT = "created_at"  # System operational execution or record creation timestamp


def validate_utc_iso8601(v: Any) -> str:
    """Validate that the string is a valid UTC ISO-8601 timestamp."""
    if not isinstance(v, str):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return str(v.astimezone(timezone.utc).isoformat())
        raise ValueError(f"Expected timestamp string or datetime, got {type(v).__name__}")

    # Parse and verify timezone
    text = v.strip()
    if not text:
        raise ValueError("Timestamp string cannot be empty")

    try:
        # datetime.fromisoformat handles 'Z' in Python 3.11+, and +00:00
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError(f"Invalid ISO-8601 timestamp: {v}") from exc

    if dt.tzinfo is None:
        raise ValueError(f"Timestamp must include timezone info (UTC): {v}")

    # Convert to UTC and format
    utc_dt = dt.astimezone(timezone.utc)
    return str(utc_dt.isoformat())


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


UtcTimestamp = Annotated[str, BeforeValidator(validate_utc_iso8601)]
