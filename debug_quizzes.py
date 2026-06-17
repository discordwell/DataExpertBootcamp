"""Debug quiz page structure."""
import asyncio
from playwright.async_api import async_playwright

from common import CDP_URL, lesson_url

QUIZZES = [
    "window-functions-wednesday-quiz",
    "fridayquiz-41956",
    "sql-aggregation-tuesdayquiz",
    "cumulative-data-quiz",
]

async def debug():
    async with async_playwright() as p:
        print("Connecting to Chrome...")
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = await context.new_page()

        for slug in QUIZZES:
            url = lesson_url(slug)
            print(f"\n{slug}:")
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(2)

            # Check page state
            info = await page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const quizBtn = buttons.find(b => b.innerText.includes('Quiz'));
                const startBtn = buttons.find(b => b.innerText.includes('Start Quiz'));
                return {
                    url: window.location.href,
                    hasQuizTab: !!quizBtn,
                    hasStartQuiz: !!startBtn,
                    buttonTexts: buttons.slice(0, 10).map(b => b.innerText.substring(0, 30))
                };
            }""")
            print(f"  URL: {info['url']}")
            print(f"  Quiz tab: {info['hasQuizTab']}")
            print(f"  Start Quiz: {info['hasStartQuiz']}")
            print(f"  Buttons: {info['buttonTexts'][:5]}")

            # Try clicking Quiz tab
            if info['hasQuizTab']:
                await page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const btn = buttons.find(b => b.innerText.includes('Quiz'));
                    if (btn) btn.click();
                }""")
                await asyncio.sleep(2)

                info2 = await page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const startBtn = buttons.find(b => b.innerText.includes('Start Quiz'));
                    return {
                        hasStartQuiz: !!startBtn,
                        pageText: document.body.innerText.substring(0, 500)
                    };
                }""")
                print(f"  After Quiz tab - Start Quiz: {info2['hasStartQuiz']}")

        await page.close()
        print("\nDone!")

asyncio.run(debug())
