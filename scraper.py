"""DataExpert Bootcamp Scraper - Extract challenge content with authenticated session."""
import browser_cookie3
import requests
import json
import re
from pathlib import Path

BASE_URL = "https://www.dataexpert.io"
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def get_session():
    """Create a requests session with Chrome cookies."""
    session = requests.Session()
    cj = browser_cookie3.chrome(domain_name='dataexpert.io')
    session.cookies = cj
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    return session


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

    return True


def extract_challenge_links(html_content):
    """Extract challenge/quiz links from page content."""
    # Look for links to quizzes or challenges
    quiz_pattern = r'href="(/[^"]*(?:quiz|challenge|lesson)[^"]*)"'
    matches = re.findall(quiz_pattern, html_content, re.IGNORECASE)
    return list(set(matches))


if __name__ == "__main__":
    print("Testing DataExpert.io authentication...")
    if test_auth():
        print("\nAuthentication successful!")
    else:
        print("\nAuthentication failed - please ensure you're logged into dataexpert.io in Chrome")
