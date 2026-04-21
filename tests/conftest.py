"""Pytest 共用 fixture。"""
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fubon_html() -> str:
    return (FIXTURES_DIR / "fubon_sample.html").read_text(encoding="utf-8")


@pytest.fixture
def histock_html() -> str:
    return (FIXTURES_DIR / "histock_sample.html").read_text(encoding="utf-8")
