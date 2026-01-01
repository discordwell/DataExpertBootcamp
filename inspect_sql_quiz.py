"""Inspect SQL quiz to see free-text input structure."""
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

        # Try a SQL quiz that had parse errors
        print("Loading SQL Window Functions quiz...")
        await page.goto("https://www.dataexpert.io/lesson/window-functions-wednesday-quiz", wait_until='networkidle', timeout=60000)
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

        # Take screenshot
        await page.screenshot(path=str(DATA_DIR / "sql_quiz_inspect.png"))
        print(f"Screenshot saved to {DATA_DIR / 'sql_quiz_inspect.png'}")

        # Get the modal HTML
        html = await page.evaluate("""
            () => {
                const modal = document.querySelector('#modal-root');
                if (modal) return modal.innerHTML;
                return document.body.innerHTML;
            }
        """)
        with open(DATA_DIR / "sql_quiz_modal.html", "w") as f:
            f.write(html)
        print(f"HTML saved to {DATA_DIR / 'sql_quiz_modal.html'}")

        # Get text content
        text = await page.evaluate("""
            () => {
                const modal = document.querySelector('#modal-root');
                if (modal) return modal.innerText;
                return document.body.innerText;
            }
        """)
        print(f"\nModal text:\n{text[:3000]}")

        # Check for textarea or input elements
        inputs = await page.evaluate("""
            () => {
                const modal = document.querySelector('#modal-root') || document.body;
                const textareas = modal.querySelectorAll('textarea');
                const inputs = modal.querySelectorAll('input[type=text]');
                const codeEditors = modal.querySelectorAll('[class*=editor], [class*=code], [class*=monaco]');
                return {
                    textareas: textareas.length,
                    textInputs: inputs.length,
                    codeEditors: codeEditors.length,
                    textareaInfo: Array.from(textareas).map(t => ({
                        id: t.id,
                        class: t.className,
                        placeholder: t.placeholder
                    })),
                    inputInfo: Array.from(inputs).map(i => ({
                        id: i.id,
                        class: i.className,
                        placeholder: i.placeholder
                    }))
                };
            }
        """)
        print(f"\nInput elements found:")
        print(f"  Textareas: {inputs['textareas']}")
        print(f"  Text inputs: {inputs['textInputs']}")
        print(f"  Code editors: {inputs['codeEditors']}")
        if inputs['textareaInfo']:
            print(f"  Textarea details: {inputs['textareaInfo']}")
        if inputs['inputInfo']:
            print(f"  Input details: {inputs['inputInfo']}")

        await page.close()

asyncio.run(inspect())
