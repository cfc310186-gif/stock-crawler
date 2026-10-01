from __future__ import annotations

import requests

import main


class FakeResponse:
    def __init__(self, body: bytes = b"ok") -> None:
        self.content = body

    def raise_for_status(self) -> None:
        return None


def test_fetch_fubon_html_retries_transient_timeout(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_get(url, headers, timeout):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.Timeout("temporary timeout")
        return FakeResponse("成功".encode("big5"))

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.time, "sleep", lambda _seconds: None)

    result = main.fetch_fubon_html("https://example.test", {"User-Agent": "test"})

    assert result == "成功"
    assert calls["count"] == 2


def test_fetch_fubon_html_raises_after_exhausted_retries(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_get(url, headers, timeout):  # noqa: ANN001
        calls["count"] += 1
        raise requests.Timeout("still down")

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.time, "sleep", lambda _seconds: None)

    try:
        main.fetch_fubon_html("https://example.test", {"User-Agent": "test"})
    except RuntimeError as exc:
        assert "重試 3 次後仍失敗" in str(exc)
    else:
        raise AssertionError("fetch_fubon_html should fail after retries")

    assert calls["count"] == main.FUBON_MAX_ATTEMPTS
