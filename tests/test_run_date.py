from __future__ import annotations

import datetime

import pytest

from lib.run_date import TARGET_DATE_ENV, resolve_target_date


def test_resolve_target_date_defaults_to_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TARGET_DATE_ENV, raising=False)

    target_date, from_env = resolve_target_date(today=datetime.date(2026, 6, 1))

    assert target_date == datetime.date(2026, 6, 1)
    assert from_env is False


def test_resolve_target_date_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TARGET_DATE_ENV, "2026-05-29")

    target_date, from_env = resolve_target_date(today=datetime.date(2026, 6, 1))

    assert target_date == datetime.date(2026, 5, 29)
    assert from_env is True


def test_resolve_target_date_rejects_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TARGET_DATE_ENV, "2026/05/29")

    with pytest.raises(ValueError, match="TARGET_DATE must use YYYY-MM-DD"):
        resolve_target_date(today=datetime.date(2026, 6, 1))
