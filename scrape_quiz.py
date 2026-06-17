"""Scrape quiz pages and extract questions."""
import asyncio
import json
import re
from playwright.async_api import async_playwright

from common import DATA_DIR, get_cookies_for_playwright, lesson_url


async def scrape_quiz(slug: str):
    """Scrape a quiz page and extract questions."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        cookies = get_cookies_for_playwright()
        await context.add_cookies(cookies)

        page = await context.new_page()

        url = lesson_url(slug)
        print(f"Loading: {url}")
        await page.goto(url, wait_until='networkidle', timeout=60000)

        if "/sign-in" in page.url:
            print("Not authenticated")
            await browser.close()
            return None

        await asyncio.sleep(2)

        # Click the Quiz tab
        quiz_tab = await page.query_selector('button:has-text("Quiz")')
        if quiz_tab:
            print("Clicking Quiz tab...")
            await quiz_tab.click()
            await asyncio.sleep(2)

        # Click the first Start Quiz button (opens modal)
        start_btn1 = await page.query_selector('button:has-text("Start Quiz")')
        if start_btn1:
            print("Clicking first Start Quiz button...")
            await start_btn1.click()
            await asyncio.sleep(2)

        # Click the Start Quiz button in the modal
        # The modal should now be visible - there will be multiple Start Quiz buttons
        start_buttons = await page.query_selector_all('button:has-text("Start Quiz")')
        print(f"Found {len(start_buttons)} Start Quiz buttons")
        if len(start_buttons) > 1:
            print("Clicking Start Quiz in modal...")
            await start_buttons[-1].click()  # Click the last one (modal)
            await asyncio.sleep(3)

        # Take screenshot
        await page.screenshot(path=str(DATA_DIR / f"quiz_{slug}_active.png"), full_page=True)

        # Now extract the quiz content
        quiz_data = await page.evaluate("""
            () => {
                const result = {
                    pageText: document.body.innerText,
                    questions: [],
                    inputs: []
                };

                // Find radio/checkbox inputs
                const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
                for (const inp of inputs) {
                    let labelText = '';
                    const label = inp.closest('label');
                    if (label) {
                        labelText = label.innerText.trim();
                    } else if (inp.parentElement) {
                        labelText = inp.parentElement.innerText.trim();
                    }

                    result.inputs.push({
                        type: inp.type,
                        name: inp.name,
                        value: inp.value,
                        id: inp.id,
                        label: labelText.substring(0, 500)
                    });
                }

                return result;
            }
        """)

        # Save the data
        with open(DATA_DIR / f"quiz_{slug}_content.json", "w") as f:
            json.dump(quiz_data, f, indent=2)

        with open(DATA_DIR / f"quiz_{slug}_text.txt", "w") as f:
            f.write(quiz_data['pageText'])

        print(f"\nInput elements found: {len(quiz_data['inputs'])}")
        for inp in quiz_data['inputs'][:10]:
            print(f"  [{inp['type']}] {inp['label'][:100]}...")

        print("\n--- Page Text ---")
        print(quiz_data['pageText'])

        await browser.close()
        return quiz_data


async def main():
    slug = "cumulative-data-quiz"
    print(f"Scraping quiz: {slug}")
    await scrape_quiz(slug)


if __name__ == "__main__":
    asyncio.run(main())
