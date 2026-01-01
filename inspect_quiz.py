"""Inspect quiz HTML structure to understand DOM."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

DATA_DIR = Path(__file__).parent / "data"

async def inspect():
    async with async_playwright() as p:
        print("Connecting to Chrome...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = await context.new_page()

        print("Loading quiz...")
        await page.goto("https://www.dataexpert.io/lesson/cumulative-data-quiz", wait_until='networkidle', timeout=60000)
        await asyncio.sleep(2)

        # Click Quiz tab
        await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText.includes('Quiz'));
                if (btn) btn.click();
            }
        """)
        await asyncio.sleep(2)

        # Click Start Quiz
        await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText.includes('Start Quiz'));
                if (btn) btn.click();
            }
        """)
        await asyncio.sleep(1.5)

        # Click modal Start Quiz
        await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btns = buttons.filter(b => b.innerText.includes('Start Quiz'));
                if (btns.length > 0) btns[btns.length-1].click();
            }
        """)
        await asyncio.sleep(2)

        # Get the modal/dialog content
        html = await page.evaluate("""
            () => {
                const modal = document.querySelector('[role="dialog"]');
                if (modal) return modal.innerHTML;
                return document.body.innerHTML;
            }
        """)

        # Save HTML for inspection
        with open(DATA_DIR / "quiz_modal.html", "w") as f:
            f.write(html)
        print(f"Saved modal HTML to {DATA_DIR / 'quiz_modal.html'}")

        # Get text content
        text = await page.evaluate("""
            () => {
                const modal = document.querySelector('[role="dialog"]');
                if (modal) return modal.innerText;
                return document.body.innerText;
            }
        """)
        print(f"\nModal text:\n{text[:2000]}")

        # Try different selectors to find options
        tests = [
            ("labels", "document.querySelectorAll('label')"),
            ("inputs", "document.querySelectorAll('input[type=radio], input[type=checkbox]')"),
            ("divs with role option", "document.querySelectorAll('[role=option]')"),
            ("divs with role button", "document.querySelectorAll('[role=button]')"),
            ("clickable divs", "document.querySelectorAll('div[class*=option], div[class*=choice], div[class*=answer]')"),
            ("cards by class", "document.querySelectorAll('[class*=card]')"),
            ("all buttons", "document.querySelectorAll('button')"),
        ]

        for name, selector in tests:
            count = await page.evaluate(f"() => {selector}.length")
            if count > 0:
                texts = await page.evaluate(f"""
                    () => Array.from({selector}).slice(0, 10).map(e => e.innerText.substring(0, 60))
                """)
                print(f"\n{name}: {count} elements")
                for t in texts:
                    print(f"  - {t}")

        # Screenshot
        await page.screenshot(path=str(DATA_DIR / "inspect_quiz.png"))
        print(f"\nSaved screenshot to {DATA_DIR / 'inspect_quiz.png'}")

        await page.close()

asyncio.run(inspect())
