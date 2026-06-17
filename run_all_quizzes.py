"""Run all DataExpert quizzes - Fixed with correct button selectors"""
import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright

from common import CDP_URL, DATA_DIR, lesson_url
from quiz_heuristics import get_answer
from quizzes import CURRICULUM


async def solve_single_quiz(page, slug: str, title: str) -> dict:
    """Solve a single quiz with correct DOM selectors."""
    result = {"slug": slug, "title": title, "questions": [], "completed": False, "score": 0}

    try:
        url = lesson_url(slug)
        print(f"\n  [{title}]", flush=True)
        await page.goto(url, wait_until='networkidle', timeout=60000)

        if "/sign-in" in page.url:
            print("    NOT LOGGED IN - Please log in to Chrome", flush=True)
            return result

        await asyncio.sleep(2)

        # Click Quiz tab using JavaScript
        clicked = await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText.trim() === 'Quiz' || b.innerText.includes('Quiz'));
                if (btn) { btn.click(); return true; }
                return false;
            }
        """)
        if not clicked:
            print("    Quiz tab not found", flush=True)
            return result
        await asyncio.sleep(2)

        # Click Start Quiz button
        await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText.includes('Start Quiz'));
                if (btn) btn.click();
            }
        """)
        await asyncio.sleep(1.5)

        # Click Start Quiz in modal (there's often a confirmation modal)
        await page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btns = buttons.filter(b => b.innerText.includes('Start Quiz'));
                if (btns.length > 0) btns[btns.length-1].click();
            }
        """)
        await asyncio.sleep(2)

        # Process questions - keep track of last question to detect stuck state
        last_question = ""
        stuck_count = 0

        for q_num in range(30):  # Max 30 questions
            # Extract question and options using correct selectors
            # Options are buttons inside div.space-y-3 within the modal
            quiz_data = await page.evaluate("""
                () => {
                    const text = document.body.innerText;

                    // Check if quiz is complete
                    if (text.includes('Quiz Complete') || text.includes('You passed') || text.includes('passed!')) {
                        return { completed: true };
                    }

                    // Find question number (e.g., "Question 1 of 6")
                    const qMatch = text.match(/Question (\\d+) of (\\d+)/);
                    if (!qMatch) {
                        return { noQuestion: true };
                    }

                    const currentQ = parseInt(qMatch[1]);
                    const totalQ = parseInt(qMatch[2]);

                    // Get question text from the modal
                    // The question is inside a div with specific styling containing the question text
                    const modal = document.querySelector('#modal-root') || document.body;

                    // Find the question - it's in a p tag inside the modal header area
                    let question = '';
                    const questionContainer = modal.querySelector('[data-testid="modal-body"]');
                    if (questionContainer) {
                        const questionP = questionContainer.querySelector('.text-lg.font-semibold p');
                        if (questionP) {
                            question = questionP.innerText.trim();
                        }
                    }

                    // If not found, try alternative parsing
                    if (!question) {
                        const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                        for (let i = 0; i < lines.length; i++) {
                            if (lines[i].includes('% Complete') && i + 1 < lines.length) {
                                // Skip "Single Choice" or "Multiple Choice" lines
                                for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
                                    if (lines[j] !== 'Single Choice' && lines[j] !== 'Multiple Choice' && lines[j].length > 10) {
                                        question = lines[j];
                                        break;
                                    }
                                }
                                break;
                            }
                        }
                    }

                    // Get options - they are buttons inside div.space-y-3
                    const options = [];
                    const optionContainer = modal.querySelector('.space-y-3');
                    if (optionContainer) {
                        const optionButtons = optionContainer.querySelectorAll('button');
                        optionButtons.forEach(btn => {
                            const pTag = btn.querySelector('p');
                            if (pTag) {
                                options.push(pTag.innerText.trim());
                            } else {
                                const text = btn.innerText.trim();
                                if (text && text.length > 3) {
                                    options.push(text);
                                }
                            }
                        });
                    }

                    return {
                        currentQ,
                        totalQ,
                        question,
                        options,
                        completed: false
                    };
                }
            """)

            if quiz_data.get('completed'):
                result["completed"] = True
                break

            if quiz_data.get('noQuestion'):
                # No question found - might be on results page
                text = await page.evaluate("document.body.innerText")
                if "passed" in text.lower() or "complete" in text.lower():
                    result["completed"] = True
                break

            question = quiz_data.get('question', '')
            options = quiz_data.get('options', [])

            # Detect if we're stuck on the same question
            if question == last_question:
                stuck_count += 1
                if stuck_count >= 3:
                    print(f"    Stuck on same question, moving on", flush=True)
                    break
            else:
                stuck_count = 0
                last_question = question

            if not question or len(options) < 2:
                print(f"    Q{q_num+1}: Parse error (q='{question[:30] if question else 'None'}...', opts={len(options)})", flush=True)
                # Take a screenshot for debugging
                await page.screenshot(path=str(DATA_DIR / f"error_{slug}_q{q_num+1}.png"))
                break

            # Get the best answer
            answer_idx = get_answer(question, options)
            answer_text = options[answer_idx] if answer_idx < len(options) else options[0]

            # Click the answer option - options are buttons inside div.space-y-3
            click_result = await page.evaluate("""
                (answerIdx) => {
                    const modal = document.querySelector('#modal-root') || document.body;
                    const optionContainer = modal.querySelector('.space-y-3');
                    if (!optionContainer) return 'no container';

                    const buttons = optionContainer.querySelectorAll('button');
                    if (buttons.length > answerIdx) {
                        buttons[answerIdx].click();
                        return 'clicked';
                    }
                    return 'button not found';
                }
            """, answer_idx)

            await asyncio.sleep(0.5)

            # Click Check Answer button
            await page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const btn = buttons.find(b => b.innerText.includes('Check Answer'));
                    if (btn && !btn.disabled) btn.click();
                }
            """)
            await asyncio.sleep(1.5)

            # Check if answer was correct
            result_text = await page.evaluate("document.body.innerText")
            # Look for "Correct!" or check for absence of "Incorrect"
            correct = "Correct!" in result_text or ("Correct" in result_text and "Incorrect" not in result_text)

            result["questions"].append({
                "q": question[:150],
                "a": answer_text[:100],
                "correct": correct
            })
            if correct:
                result["score"] += 1

            status = "✓" if correct else "✗"
            print(f"    Q{q_num+1}: {status} {question[:50]}...", flush=True)

            # Click Next/Continue button
            await page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    // Try Next first, then Continue
                    let btn = buttons.find(b => b.innerText.trim() === 'Next' || b.innerText.includes('Next'));
                    if (!btn) {
                        btn = buttons.find(b => b.innerText.includes('Continue'));
                    }
                    if (btn && !btn.disabled) btn.click();
                }
            """)
            await asyncio.sleep(1)

        # Print quiz summary
        total = len(result["questions"])
        if total > 0:
            pct = (result["score"] / total) * 100
            status = "PASSED" if pct >= 70 else f"{pct:.0f}%"
            print(f"    → {result['score']}/{total} ({status})", flush=True)
            if pct >= 70:
                result["completed"] = True

    except Exception as e:
        print(f"    ERROR: {str(e)[:80]}", flush=True)
        import traceback
        traceback.print_exc()

    return result


async def run_all_quizzes():
    """Run all quizzes."""
    all_results = {"timestamp": datetime.now().isoformat(), "weeks": {}}

    async with async_playwright() as p:
        print("Connecting to Chrome...", flush=True)
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"ERROR: Could not connect to Chrome: {e}", flush=True)
            print("Make sure Chrome is running with: --remote-debugging-port=9222", flush=True)
            return None

        context = browser.contexts[0]
        page = await context.new_page()

        for week_name, quizzes in CURRICULUM.items():
            print(f"\n{'='*60}", flush=True)
            print(f"{week_name}", flush=True)
            print('='*60, flush=True)

            week_results = []
            for slug, title in quizzes:
                result = await solve_single_quiz(page, slug, title)
                week_results.append(result)

                # Save progress after each quiz
                all_results["weeks"][week_name] = week_results
                with open(DATA_DIR / "quiz_progress.json", "w") as f:
                    json.dump(all_results, f, indent=2)

            # Week summary
            completed = sum(1 for r in week_results if r["completed"])
            total_q = sum(len(r["questions"]) for r in week_results)
            total_c = sum(r["score"] for r in week_results)
            pct = (total_c/total_q*100) if total_q > 0 else 0
            print(f"\n  WEEK SUMMARY: {completed}/{len(quizzes)} passed, {total_c}/{total_q} correct ({pct:.0f}%)", flush=True)

        await page.close()

    # Save final results
    with open(DATA_DIR / "all_quiz_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n{'='*60}", flush=True)
    print("ALL QUIZZES COMPLETE!", flush=True)
    print('='*60, flush=True)

    # Final summary
    total_passed = sum(sum(1 for r in week if r["completed"]) for week in all_results["weeks"].values())
    total_quizzes = sum(len(week) for week in all_results["weeks"].values())
    print(f"Passed: {total_passed}/{total_quizzes} quizzes", flush=True)

    return all_results


if __name__ == "__main__":
    print("DataExpert Quiz Runner", flush=True)
    print("="*40, flush=True)
    asyncio.run(run_all_quizzes())
