"""Shared configuration and authentication helpers for the DataExpert scripts.

Every script in this repo talks to the same site, writes to the same ``data/``
directory, and reuses the logged-in Chrome session's cookies. Those three things
used to be copy-pasted into each file; they now live here so there is a single
source of truth.

Authentication works by reading cookies straight out of the local Chrome profile
(via ``browser_cookie3``) — you log into dataexpert.io once in your normal
browser and the scripts reuse that session. Nothing here stores or transmits
credentials.
"""
from pathlib import Path

import browser_cookie3
import requests

BASE_URL = "https://www.dataexpert.io"

# All scraped HTML, screenshots, and progress JSON land here. Git-ignored.
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

COOKIE_DOMAIN = "dataexpert.io"

# Chrome DevTools Protocol endpoint. The CDP-based runners attach to a Chrome
# you started with ``--remote-debugging-port=9222`` so they drive your real,
# already-authenticated tab instead of re-logging in. This used to be a literal
# ``"http://localhost:9222"`` repeated in every runner.
CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"


def lesson_url(slug: str) -> str:
    """Return the full lesson/quiz URL for a lesson ``slug``.

    Every runner and scraper navigates to ``{BASE_URL}/lesson/{slug}``; this
    keeps that pattern in one place so a site change only needs editing here.
    """
    return f"{BASE_URL}/lesson/{slug}"


def get_cookies_for_playwright(domain: str = COOKIE_DOMAIN) -> list:
    """Read Chrome cookies for ``domain`` and convert them to Playwright format.

    Returns a list of dicts shaped for ``BrowserContext.add_cookies``. The
    ``domain``/``path`` fields fall back to sane defaults when Chrome leaves them
    empty, and ``expires`` is only set when present so session cookies stay as
    session cookies.
    """
    cj = browser_cookie3.chrome(domain_name=domain)
    cookies = []
    for c in cj:
        cookie = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain if c.domain else f".{COOKIE_DOMAIN}",
            "path": c.path if c.path else "/",
        }
        if c.expires:
            cookie["expires"] = c.expires
        cookies.append(cookie)
    return cookies


def get_session(domain: str = COOKIE_DOMAIN) -> requests.Session:
    """Create a ``requests`` session pre-loaded with the logged-in Chrome cookies.

    Use this for plain HTTP scraping where a full browser isn't needed.
    """
    session = requests.Session()
    session.cookies = browser_cookie3.chrome(domain_name=domain)
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    )
    return session
