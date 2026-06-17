"""DataExpert Bootcamp Quiz Solver - Connects to existing Chrome with remote debugging."""
import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright

from common import CDP_PORT, CDP_URL, DATA_DIR, lesson_url
from quiz_heuristics import get_answer


async def solve_quiz(slug: str, module_name: str = ""):
    """Navigate through a quiz using CDP connection to existing Chrome."""
    quiz_data = {
        "slug": slug,
        "module": module_name,
        "questions": [],
        "completed": False,
        "timestamp": datetime.now().isoformat()
    }

    async with async_playwright() as p:
        print(f"Connecting to Chrome on port {CDP_PORT}...")
        print("Make sure Chrome is running with: open -a 'Google Chrome' --args --remote-debugging-port=9222")

        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"\nERROR: Could not connect to Chrome: {e}")
            print("\nTo fix this:")
            print("1. Close all Chrome windows")
            print("2. Run: open -a 'Google Chrome' --args --remote-debugging-port=9222")
            print("3. Log into dataexpert.io in Chrome")
            print("4. Run this script again")
            return None

        # Get or create a page
        contexts = browser.contexts
        if not contexts:
            print("No browser contexts found")
            return None

        context = contexts[0]
        pages = context.pages

        # Find or create dataexpert page
        page = None
        for p in pages:
            if "dataexpert" in p.url:
                page = p
                break

        if not page:
            page = await context.new_page()

        url = lesson_url(slug)
        print(f"\n{'='*60}")
        print(f"Quiz: {slug}")
        print(f"{'='*60}")

        await page.goto(url, wait_until='networkidle', timeout=60000)

        # Check if logged in
        if "/sign-in" in page.url:
            print("Not logged in. Please log in Chrome and try again.")
            return None

        await asyncio.sleep(2)

        # Navigate to quiz tab
        quiz_tab = await page.query_selector('button:has-text("Quiz")')
        if quiz_tab:
            await quiz_tab.click()
            await asyncio.sleep(2)

        # Start quiz
        start_btn = await page.query_selector('button:has-text("Start Quiz")')
        if start_btn:
            await start_btn.click()
            await asyncio.sleep(1)

        # Click modal start button
        start_buttons = await page.query_selector_all('button:has-text("Start Quiz")')
        if len(start_buttons) > 1:
            await start_buttons[-1].click()
            await asyncio.sleep(2)

        # Process questions
        question_num = 1
        max_questions = 20

        while question_num <= max_questions:
            await asyncio.sleep(1)
            page_text = await page.evaluate("document.body.innerText")

            # Check completion
            if "Quiz Complete" in page_text or "You passed" in page_text:
                print("\n✓ Quiz completed!")
                quiz_data["completed"] = True
                break

            # Find question info
            q_match = re.search(r'Question (\d+) of (\d+)', page_text)
            if not q_match:
                if "passed" in page_text.lower() or "complete" in page_text.lower():
                    quiz_data["completed"] = True
                print("Quiz complete or could not find question")
                break

            current_q = int(q_match.group(1))
            total_q = int(q_match.group(2))

            # Parse question and options
            lines = [l.strip() for l in page_text.split('\n') if l.strip()]
            question_text = ""
            options = []

            # Find question after "X% Complete"
            for i, line in enumerate(lines):
                if "% Complete" in line and i + 1 < len(lines):
                    question_text = lines[i + 1]
                    break

            # Find options between "Single/Multiple Choice" and "Show Hint"
            in_options = False
            for line in lines:
                if "Single Choice" in line or "Multiple Choice" in line:
                    in_options = True
                    continue
                if in_options:
                    if "Show Hint" in line or "Check Answer" in line:
                        break
                    if line and line not in ["Notes", "Quiz", "Previous", "Next", "Module"]:
                        options.append(line)

            options = options[:6]

            if not question_text or not options:
                print(f"Parse error at Q{current_q}")
                await page.screenshot(path=str(DATA_DIR / f"quiz_{slug}_error.png"))
                break

            print(f"\nQ{current_q}/{total_q}: {question_text[:100]}")
            for i, opt in enumerate(options):
                print(f"  {i+1}. {opt[:70]}")

            # Get answer
            answer_idx = get_answer(question_text, options)
            print(f"  → Answer: {answer_idx + 1}")

            quiz_data["questions"].append({
                "number": current_q,
                "question": question_text,
                "options": options,
                "selected": answer_idx
            })

            # Click the answer
            labels = await page.query_selector_all('label')
            for label in labels:
                text = await label.inner_text()
                if answer_idx < len(options) and options[answer_idx] in text:
                    await label.click()
                    break

            await asyncio.sleep(0.5)

            # Check answer
            check_btn = await page.query_selector('button:has-text("Check Answer")')
            if check_btn:
                await check_btn.click()
                await asyncio.sleep(1)

            # Record result
            result = await page.evaluate("document.body.innerText")
            if "Correct" in result:
                print("  ✓ Correct!")
                quiz_data["questions"][-1]["correct"] = True
            else:
                print("  ✗ Incorrect")
                quiz_data["questions"][-1]["correct"] = False

            # Next question
            next_btn = await page.query_selector('button:has-text("Next"), button:has-text("Continue")')
            if next_btn:
                await next_btn.click()
                await asyncio.sleep(1)
            else:
                break

            question_num += 1

        # Save results
        with open(DATA_DIR / f"quiz_{slug}_results.json", "w") as f:
            json.dump(quiz_data, f, indent=2)

        await page.screenshot(path=str(DATA_DIR / f"quiz_{slug}_final.png"))

        # Don't close the browser since it's the user's Chrome
        return quiz_data


async def main():
    print("DataExpert Quiz Solver")
    print("=" * 40)
    print("\nBefore running, make sure Chrome is started with remote debugging:")
    print("  open -a 'Google Chrome' --args --remote-debugging-port=9222")
    print("\nAnd that you're logged into dataexpert.io")
    print("")

    slug = "cumulative-data-quiz"
    result = await solve_quiz(slug, "Data Modeling: Week 1")

    if result:
        print(f"\nResults: {len(result['questions'])} questions")
        correct = sum(1 for q in result['questions'] if q.get('correct'))
        print(f"Score: {correct}/{len(result['questions'])}")


if __name__ == "__main__":
    asyncio.run(main())
