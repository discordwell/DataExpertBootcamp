"""DataExpert Bootcamp Browser Scraper - Uses nodriver for JS-rendered content."""
import asyncio
import nodriver as uc
import json
import re

from common import BASE_URL, DATA_DIR


async def human_delay(min_sec=1.0, max_sec=2.0):
    import random
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def get_curriculum_content():
    """Scrape the curriculum page with nodriver."""
    # Use Chrome's default profile to get existing cookies
    profile_dir = DATA_DIR / "browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    config = uc.Config()
    config.sandbox = False
    config.headless = False  # Set to True once validated

    browser = await uc.start(config=config)

    try:
        # Navigate to curriculum page
        url = f"{BASE_URL}/program/data-challenge/details?tab=curriculum"
        print(f"Navigating to: {url}")
        page = await browser.get(url)

        await human_delay(3, 5)

        # Check page title
        title = await page.evaluate("document.title")
        print(f"Page title: {title}")

        # Check current URL - might need to login
        current_url = await page.evaluate("window.location.href")
        print(f"Current URL: {current_url}")

        if "/sign-in" in current_url or "/login" in current_url:
            print("\nNeed to login - please log in manually in the browser")
            print("Waiting up to 120 seconds for login...")
            for i in range(60):
                await human_delay(2, 2)
                current_url = await page.evaluate("window.location.href")
                if "/sign-in" not in current_url and "/login" not in current_url:
                    print("Login detected!")
                    await human_delay(3, 5)
                    break
                if i % 15 == 0:
                    print(f"  Still waiting... ({i*2}s)")

        # Wait for content to load
        print("Waiting for curriculum content to load...")
        await human_delay(5, 8)

        # Get the full page HTML
        html = await page.evaluate("document.documentElement.outerHTML")
        with open(DATA_DIR / "curriculum_rendered.html", "w") as f:
            f.write(html)
        print(f"Saved rendered HTML ({len(html)} chars)")

        # Extract all links that look like lessons/quizzes
        links = await page.evaluate("""
            (() => {
                const links = Array.from(document.querySelectorAll('a'));
                return links.map(a => ({
                    href: a.href,
                    text: a.innerText.trim().substring(0, 100)
                })).filter(l => l.href.includes('dataexpert.io'));
            })()
        """)

        print(f"\nFound {len(links)} internal links")

        # Filter for lesson/challenge links
        challenge_links = [l for l in links if any(x in l['href'].lower() for x in ['lesson', 'quiz', 'challenge', 'module', 'week'])]
        print(f"Challenge-related links: {len(challenge_links)}")

        for link in challenge_links[:20]:
            print(f"  {link['text'][:50]}: {link['href']}")

        # Save all links
        with open(DATA_DIR / "all_links.json", "w") as f:
            json.dump(links, f, indent=2)

        with open(DATA_DIR / "challenge_links.json", "w") as f:
            json.dump(challenge_links, f, indent=2)

        return challenge_links

    finally:
        print("\nClosing browser...")
        browser.stop()


if __name__ == "__main__":
    print("Starting DataExpert curriculum scraper...")
    asyncio.run(get_curriculum_content())
