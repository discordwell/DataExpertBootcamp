"""DataExpert Bootcamp Scraper - Extract challenge content with authenticated session."""
import re

from common import BASE_URL, DATA_DIR, get_session


def test_auth():
    """Test if we can access authenticated content."""
    session = get_session()

    # Try to access the bootcamp curriculum page
    url = f"{BASE_URL}/program/data-challenge/details?tab=curriculum"
    response = session.get(url)

    print(f"Status: {response.status_code}")
    print(f"URL: {response.url}")
    print(f"Content length: {len(response.text)}")

    # Check if we're logged in by looking for user-specific content
    if 'sign in' in response.text.lower() or 'login' in response.url.lower():
        print("NOT AUTHENTICATED - redirected to login")
        return False

    # Save the response for inspection
    with open(DATA_DIR / "curriculum_page.html", "w") as f:
        f.write(response.text)
    print(f"Saved response to {DATA_DIR / 'curriculum_page.html'}")

    # Pull the challenge/quiz/lesson links out of the page and report them.
    links = extract_challenge_links(response.text)
    print(f"Found {len(links)} challenge/quiz/lesson links")
    for href in links[:20]:
        print(f"  {href}")

    return True


def extract_challenge_links(html_content: str) -> list:
    """Extract distinct challenge/quiz/lesson hrefs from page HTML.

    Returns the matching ``/...`` paths in first-seen order, de-duplicated. The
    pattern matches any href whose path contains ``quiz``, ``challenge``, or
    ``lesson`` (case-insensitive) — how the curriculum page links to each item.

    De-duplication preserves order (rather than going through a ``set``) so the
    output is deterministic across runs.
    """
    quiz_pattern = r'href="(/[^"]*(?:quiz|challenge|lesson)[^"]*)"'
    matches = re.findall(quiz_pattern, html_content, re.IGNORECASE)
    seen = set()
    unique = []
    for href in matches:
        if href not in seen:
            seen.add(href)
            unique.append(href)
    return unique


if __name__ == "__main__":
    print("Testing DataExpert.io authentication...")
    if test_auth():
        print("\nAuthentication successful!")
    else:
        print("\nAuthentication failed - please ensure you're logged into dataexpert.io in Chrome")
