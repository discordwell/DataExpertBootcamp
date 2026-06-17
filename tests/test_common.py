"""Tests for the shared helpers in ``common``.

The cookie helpers normally read the real Chrome profile via ``browser_cookie3``;
here we monkeypatch that call so the conversion logic can be tested offline with
no browser and no real cookies.
"""
import common


class FakeCookie:
    """Minimal stand-in for an ``http.cookiejar.Cookie``."""

    def __init__(self, name, value, domain="", path="", expires=None):
        self.name = name
        self.value = value
        self.domain = domain
        self.path = path
        self.expires = expires


def test_get_cookies_for_playwright_conversion(monkeypatch):
    fake = [
        FakeCookie("sid", "abc", ".dataexpert.io", "/", 1700000000),
        FakeCookie("session_only", "v", "", "", None),  # empty domain/path, no expiry
    ]
    monkeypatch.setattr(common.browser_cookie3, "chrome", lambda domain_name="": fake)

    cookies = common.get_cookies_for_playwright()

    assert cookies[0] == {
        "name": "sid",
        "value": "abc",
        "domain": ".dataexpert.io",
        "path": "/",
        "expires": 1700000000,
    }
    # Empty domain/path fall back to defaults; no `expires` key when it's falsy.
    assert cookies[1] == {
        "name": "session_only",
        "value": "v",
        "domain": ".dataexpert.io",
        "path": "/",
    }
    assert "expires" not in cookies[1]


def test_get_cookies_passes_domain_through(monkeypatch):
    captured = {}

    def fake_chrome(domain_name=""):
        captured["domain"] = domain_name
        return []

    monkeypatch.setattr(common.browser_cookie3, "chrome", fake_chrome)
    common.get_cookies_for_playwright("example.com")
    assert captured["domain"] == "example.com"


def test_get_session_sets_cookies_and_headers(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(common.browser_cookie3, "chrome", lambda domain_name="": sentinel)

    session = common.get_session()

    assert session.cookies is sentinel
    assert "User-Agent" in session.headers
    assert "Accept-Language" in session.headers
    # The default UA is a desktop Chrome string, matching the original scraper.
    assert "Chrome/" in common.DEFAULT_USER_AGENT


def test_data_dir_and_base_url_are_shared():
    assert common.BASE_URL == "https://www.dataexpert.io"
    assert common.DATA_DIR.name == "data"
