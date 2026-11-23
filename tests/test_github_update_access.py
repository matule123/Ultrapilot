import logging
from unittest.mock import Mock

import pytest

from core import update_check


@pytest.fixture(autouse=True)
def clean_tokens(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


def test_private_zip_uses_authenticated_api_and_pinned_commit(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "test-token")
    url, headers = update_check._archive_request("abcdef0")
    assert url == "https://api.github.com/repos/matule123/Ultrapilot/zipball/abcdef0"
    assert headers["Authorization"] == "Bearer test-token"


def test_public_zip_does_not_need_token():
    url, headers = update_check._archive_request("abcdef0")
    assert url == "https://github.com/matule123/Ultrapilot/archive/abcdef0.zip"
    assert "Authorization" not in headers


@pytest.mark.parametrize("status, message, calls", [
    (401, "rejected the update token", 1),
    (404, "not visible", 2),
    (403, "commits API returned HTTP 403", 2),
])
def test_access_error_has_distinct_diagnostic(monkeypatch, caplog, status, message, calls):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    get = Mock(return_value=Mock(status_code=status, headers={}))
    monkeypatch.setattr("requests.get", get)
    with caplog.at_level(logging.WARNING):
        assert update_check.latest_release() is None
    assert get.call_count == calls
    assert get.call_args_list[0].args[0] == (
        "https://api.github.com/repos/matule123/Ultrapilot/commits/main")
    assert message in caplog.text
    assert "test-token" not in caplog.text
