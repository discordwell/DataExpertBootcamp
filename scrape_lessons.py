"""Scrape the actual lesson content from DataExpert bootcamp."""
import asyncio
import json
from playwright.async_api import async_playwright

from common import BASE_URL, DATA_DIR, get_cookies_for_playwright


async def scrape_lesson_list():
    """Scrape the lesson list from the start page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )

        cookies = get_cookies_for_playwright()
        await context.add_cookies(cookies)
        print(f"Added {len(cookies)} cookies")

        page = await context.new_page()

        # Go to the start/lessons page
        url = f"{BASE_URL}/program/start/data-challenge"
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until='networkidle', timeout=60000)

        current_url = page.url
        print(f"Current URL: {current_url}")

        # Wait for content to load
        await asyncio.sleep(3)

        # Save screenshot
        await page.screenshot(path=str(DATA_DIR / "lessons_page.png"), full_page=True)
        print("Saved screenshot")

        # Save HTML
        html = await page.content()
        with open(DATA_DIR / "lessons_page.html", "w") as f:
            f.write(html)
        print(f"Saved HTML ({len(html)} chars)")

        # Try to find and click expandable sections
        accordions = await page.query_selector_all('[class*="accordion"], [class*="collapse"], [class*="expand"], button[aria-expanded]')
        print(f"Found {len(accordions)} potential accordion elements")

        for i, accordion in enumerate(accordions[:10]):  # Limit to first 10
            try:
                await accordion.click()
                await asyncio.sleep(0.5)
            except:
                pass

        await asyncio.sleep(2)

        # Get all links after expanding
        links = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a'));
                return links.map(a => ({
                    href: a.href,
                    text: a.innerText.trim().substring(0, 200)
                })).filter(l => l.href && l.href.includes('dataexpert.io'));
            }
        """)

        print(f"\nFound {len(links)} links after expansion")

        # Look for lesson/quiz links
        lesson_links = []
        for link in links:
            href = link['href'].lower()
            text = link['text'].lower()
            if any(k in href or k in text for k in ['lesson', 'quiz', 'challenge', 'day-', 'week-', 'module']):
                lesson_links.append(link)
                print(f"  Found: {link['text'][:60]}: {link['href']}")

        # Also look for specific patterns in URLs
        all_links_data = await page.evaluate("""
            () => {
                const allLinks = Array.from(document.querySelectorAll('a[href*="lesson"], a[href*="quiz"], a[href*="day"], a[href*="week"]'));
                return allLinks.map(a => ({
                    href: a.href,
                    text: a.innerText.trim(),
                    parent: a.closest('div, li, section')?.innerText?.substring(0, 100) || ''
                }));
            }
        """)

        print(f"\nPattern-matched links: {len(all_links_data)}")
        for link in all_links_data[:20]:
            print(f"  {link['text'][:40]}: {link['href']}")

        # Save expanded screenshot
        await page.screenshot(path=str(DATA_DIR / "lessons_expanded.png"), full_page=True)

        # Save all lesson data
        with open(DATA_DIR / "lesson_links.json", "w") as f:
            json.dump({
                'all_links': links,
                'lesson_links': lesson_links,
                'pattern_links': all_links_data
            }, f, indent=2)

        # Look at the page structure to find lesson content
        content_text = await page.evaluate("""
            () => {
                return document.body.innerText;
            }
        """)

        with open(DATA_DIR / "page_text.txt", "w") as f:
            f.write(content_text)

        print(f"\nPage text saved ({len(content_text)} chars)")

        await browser.close()
        return lesson_links


if __name__ == "__main__":
    print("Scraping lesson list...")
    asyncio.run(scrape_lesson_list())
