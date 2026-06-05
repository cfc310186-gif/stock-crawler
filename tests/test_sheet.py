from __future__ import annotations

import gspread

from lib.sheet import _open_spreadsheet_with_retries


class FlakyClient:
    def __init__(self) -> None:
        self.calls = 0

    def open(self, sheet_name: str):
        self.calls += 1
        if self.calls == 1:
            raise gspread.exceptions.SpreadsheetNotFound("temporary lookup miss")
        return {"name": sheet_name}


def test_open_spreadsheet_retries_transient_not_found() -> None:
    client = FlakyClient()

    spreadsheet = _open_spreadsheet_with_retries(
        client,
        "Stock_Data",
        attempts=2,
        delay_seconds=0,
    )

    assert spreadsheet == {"name": "Stock_Data"}
    assert client.calls == 2
