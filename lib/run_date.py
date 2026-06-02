from __future__ import annotations

import datetime
import os

TARGET_DATE_ENV = "TARGET_DATE"


def resolve_target_date(today: datetime.date | None = None) -> tuple[datetime.date, bool]:
    """Return the requested run date and whether it came from TARGET_DATE."""
    raw_value = os.environ.get(TARGET_DATE_ENV, "").strip()
    if raw_value:
        try:
            return datetime.date.fromisoformat(raw_value), True
        except ValueError as exc:
            raise ValueError(f"{TARGET_DATE_ENV} must use YYYY-MM-DD, got {raw_value!r}") from exc

    return today or datetime.date.today(), False
