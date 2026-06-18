"""Enhanced quiz runner with SQL writing support - Uses Claude for SQL solving."""
import asyncio
import json
import re
import subprocess
from datetime import datetime
from playwright.async_api import async_playwright

from common import CDP_URL, DATA_DIR, lesson_url
from quiz_parsing import clean_text_response, extract_sql, parse_mc_answer
from quiz_sql import generate_sql
from quiz_status import (
    classify_status,
    is_perfect_completion,
    is_quiz_complete,
    parse_score,
)
from quizzes import ALL_QUIZZES, CURRICULUM

RESEARCH_FILE = DATA_DIR / "quiz_research.md"


def load_research_context() -> str:
    """Load the quiz research file for context."""
    if RESEARCH_FILE.exists():
        return RESEARCH_FILE.read_text()
    return ""


def solve_mc_with_claude(question: str, options: list, multi_select: bool = False) -> list:
    """Use Claude CLI to answer a multiple choice question.

    Returns a list of indices (0-indexed). For single-select, returns [idx].
    For multi-select, may return multiple indices.
    Uses chain-of-thought prompting with structured thinking.
    """
    # Format options with letters
    options_text = "\n".join([f"{chr(65+i)}. {opt}" for i, opt in enumerate(options)])

    # Dynamically set valid letters based on option count
    num_options = len(options)
    if num_options == 2:
        valid_letters = "A or B"
    elif num_options == 3:
        valid_letters = "A, B, or C"
    else:
        valid_letters = "A, B, C, or D"

    # Load research context for difficult questions
    research_context = load_research_context()

    # Different instructions for multi-select vs single-select
    if multi_select:
        answer_instruction = f"[One or more letters, comma-separated if multiple: {valid_letters}]"
        select_instruction = "This is a MULTI-SELECT question. You may need to select MORE THAN ONE answer. Select ALL answers that are correct."
    else:
        answer_instruction = f"[Single letter only: {valid_letters}]"
        select_instruction = "This is a SINGLE-SELECT question. Choose the ONE best answer."

    prompt = f"""You are answering a multiple choice question from a data engineering bootcamp quiz.

<research_context>
{research_context}
</research_context>

<question>
{question}
</question>

<options>
{options_text}
</options>

IMPORTANT: {select_instruction}

Check the research_context above first! It contains verified correct answers for common tricky questions.

Instructions:
1. Check if this question matches any pattern in the research context - if so, use that answer
2. If this involves code, trace through it step by step
3. If this involves technical concepts, use the research context or search the web
4. For True/False questions about CDC: triggers=TRUE, row-level only=FALSE
5. For "always balanced" trees: prefer B-Tree over AVL
6. For hyperparameter tuning methods: choose "All of the above" if available
7. For MULTI-SELECT: carefully consider if multiple options could be correct

<thinking>
[Your analysis here]
</thinking>

<answer>
{answer_instruction}
</answer>"""

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120  # Increased timeout for research context + thinking
        )
        response = result.stdout.strip()
        # Parsing the model's letters out of the response is pure logic, unit
        # tested in tests/test_quiz_parsing.py.
        return parse_mc_answer(response, num_options, multi_select)
    except Exception as e:
        print(f"         Claude MC exception: {e}", flush=True)
        return [0]


def solve_text_response_with_claude(question: str, feedback: str = None) -> str:
    """Use Claude CLI to answer a free-form text response question (design questions, etc.)."""

    prompt_parts = [
        "You are answering a data engineering interview question. Write a thoughtful, detailed response.",
        "",
        f"**Question:** {question}",
        "",
    ]

    if feedback:
        prompt_parts.extend([
            "**Previous attempt feedback:**",
            feedback,
            "",
            "Please improve your answer based on this feedback.",
            ""
        ])

    prompt_parts.extend([
        "REQUIREMENTS:",
        "1. Be specific and detailed in your answer",
        "2. If asked about data modeling, describe specific tables, columns, and relationships",
        "3. Use technical terminology appropriately",
        "4. Structure your answer clearly (use bullet points or numbered lists where appropriate)",
        "5. Keep your response concise but complete (2-4 paragraphs or equivalent)",
        "6. Return ONLY your answer - no preamble like 'Here is my answer:'",
        "",
        "Your response:"
    ])

    prompt = "\n".join(prompt_parts)

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60
        )
        response = result.stdout.strip()
        if not response:
            response = result.stderr.strip()

        # Clean up response - remove any leading "Here is" type phrasing
        response = clean_text_response(response)

        return response if response else "Unable to generate response"
    except subprocess.TimeoutExpired:
        print(f"         Claude timed out", flush=True)
        return "Unable to generate response - timeout"
    except Exception as e:
        print(f"         Claude exception: {e}", flush=True)
        return None


def solve_sql_with_claude(question: str, table: str, expected_cols: list, feedback: str = None, sample_data: str = None) -> str:
    """Use Claude CLI to solve a SQL problem, with optional feedback for iteration.

    Args:
        question: The SQL question text (FULL text including examples)
        table: The table name to query
        expected_cols: List of dicts with 'name' and 'type' keys, e.g. [{'name': 'id', 'type': 'integer'}]
        feedback: Optional feedback from previous attempt
        sample_data: Optional sample data from the table (SELECT * LIMIT 3 output)
    """

    # Format columns with types for the prompt
    if expected_cols and isinstance(expected_cols[0], dict):
        col_specs = [f"{c['name']} ({c['type']})" for c in expected_cols]
        col_names = [c['name'] for c in expected_cols]
    else:
        # Fallback for simple list of column names
        col_specs = expected_cols
        col_names = expected_cols

    prompt_parts = [
        "You are solving a SQL quiz question. The database uses Trino/Presto SQL syntax.",
        "",
        f"**Question:** {question}",
        "",
        f"**Available Table:** {table}",
        "",
    ]

    # Add sample data if available - this helps Claude understand the actual table structure
    if sample_data:
        prompt_parts.extend([
            "**Sample Data from Table (SELECT * LIMIT 3):**",
            "```",
            sample_data,
            "```",
            "",
        ])

    prompt_parts.append("**Expected Output Columns (in exact order with data types):**")

    # Add each column on its own line for clarity
    for i, spec in enumerate(col_specs, 1):
        prompt_parts.append(f"  {i}. {spec}")

    prompt_parts.append("")

    if feedback:
        prompt_parts.extend([
            "**Previous attempt feedback:**",
            feedback,
            "",
            "Please fix the SQL based on this feedback.",
            ""
        ])

    prompt_parts.extend([
        "CRITICAL REQUIREMENTS:",
        f"1. SELECT columns in EXACT order: {', '.join(col_names)}",
        "2. Column names must match EXACTLY (use AS to rename if needed)",
        "3. Use Trino/Presto SQL syntax (NOT PostgreSQL)",
        "4. Do NOT use DISTINCT ON (use ROW_NUMBER() OVER instead)",
        "5. Do NOT use INTERVAL syntax like '30 minutes' - use date_diff() or date_add() functions",
        "6. Return ONLY the SQL query - no explanations, no markdown",
        "",
        "TRINO JSON FUNCTIONS (use these, not PostgreSQL syntax):",
        "- json_extract_scalar(column, '$.field') - returns VARCHAR",
        "- json_extract(column, '$.array') - returns JSON",
        "- CAST(json_extract(col, '$.items') AS ARRAY(ROW(sku VARCHAR, price DOUBLE, qty INTEGER))) - for arrays",
        "- Use CROSS JOIN UNNEST(...) AS t(field1, field2) to flatten arrays",
        "",
        "HOW TO INTERPRET VALIDATION ERRORS:",
        "- 'Right answer has N rows. Your query has M rows' → Use WHERE to filter, NOT LIMIT or ORDER BY",
        "  Example: 'Only include items where total_price > 25' means WHERE total_price > 25",
        "- 'Value should be X but value is Y' → Check your WHERE/filter conditions",
        "- 'column: region ! Value should be US but value is null' → The field is in a nested location",
        "  Check the sample data to find where region/channel are located (maybe inside items array)",
        "",
        "SQL:"
    ])

    prompt = "\n".join(prompt_parts)

    try:
        # Call Claude CLI with the prompt in print mode (non-interactive)
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            # Extracting/normalizing the SQL out of the model's response is pure
            # logic, unit tested in tests/test_quiz_parsing.py.
            sql = extract_sql(result.stdout)
            if sql:
                return sql
            print(f"         Invalid SQL response: {result.stdout.strip()[:50]}...", flush=True)
            return None
        else:
            print(f"         Claude error: {result.stderr[:100]}", flush=True)
            return None
    except subprocess.TimeoutExpired:
        print("         Claude timeout", flush=True)
        return None
    except Exception as e:
        print(f"         Claude exception: {e}", flush=True)
        return None


# The quiz curriculum (ALL_QUIZZES flat list + CURRICULUM week grouping) lives in
# quizzes.py so this runner and run_all_quizzes.py share one source of truth.
#
# NOTE: This runner answers every question type via the Claude CLI
# (see solve_mc_with_claude / solve_sql_with_claude above). The offline
# fallbacks live in their own pure, tested modules: the keyword heuristic in
# quiz_heuristics.get_answer and the template-based SQL generator in
# quiz_sql.generate_sql (imported at the top).


async def solve_quiz(page, slug: str, title: str) -> dict:
    """Solve a quiz with both multiple choice and SQL writing support."""
    result = {"slug": slug, "title": title, "questions": [], "completed": False, "score": 0}

    try:
        url = lesson_url(slug)
        print(f"\n  [{title}]", flush=True)
        await page.goto(url, wait_until='networkidle', timeout=60000)

        if "/sign-in" in page.url:
            print("    NOT LOGGED IN", flush=True)
            return result

        await asyncio.sleep(2)

        # Check if already completed - but only skip if perfect score (100%)
        page_text = await page.evaluate("document.body.innerText")
        if "Lesson Completed" in page_text and "passed the quiz" in page_text.lower():
            # Score parsing + the "already perfect, skip" rule live in quiz_status
            # (pure, tested). The score regex used to be inlined here and at two
            # other call sites; it deliberately requires a trailing "(N%)" so it
            # matches a quiz score like "5/5 (100%)" and not a date like 26/12/2025.
            score = parse_score(page_text)
            is_perfect = is_perfect_completion(page_text)
            if score is not None:
                state = "Already perfect" if is_perfect else "Completed but not perfect"
                verb = "skipping" if is_perfect else "retaking"
                print(f"    {state} ({score.got}/{score.total} = {score.pct}%) - {verb}", flush=True)
            elif is_perfect:
                print("    Already perfect (100%) - skipping", flush=True)
            else:
                print("    Completed (score pattern not found) - retaking", flush=True)

            if is_perfect:
                result["completed"] = True
                result["score"] = 1
                return result
            # If not perfect, continue to retake the quiz

        # Click Quiz tab
        clicked = await page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const btn = buttons.find(b => b.innerText.trim() === 'Quiz');
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        if not clicked:
            print("    Quiz tab not found", flush=True)
            return result

        await asyncio.sleep(2)

        # Check again after clicking Quiz tab - only skip if perfect
        page_text = await page.evaluate("document.body.innerText")
        if "Lesson Completed" in page_text or "successfully passed" in page_text.lower():
            # Same "already perfect, skip" rule as above, via quiz_status.
            score = parse_score(page_text)
            if is_perfect_completion(page_text):
                label = f"{score.got}/{score.total} = {score.pct}%" if score is not None else "100%"
                print(f"    Already perfect ({label}) - skipping", flush=True)
                result["completed"] = True
                result["score"] = 1
                return result
            elif score is not None:
                print(f"    Not perfect ({score.got}/{score.total} = {score.pct}%) - retaking", flush=True)
            # Continue to retake if not perfect or score unknown

        # Click Start Quiz button
        await page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const btn = buttons.find(b => b.innerText.includes('Start Quiz'));
            if (btn) btn.click();
        }""")
        await asyncio.sleep(1.5)

        # Click Start Quiz in modal if present
        await page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const btns = buttons.filter(b => b.innerText.includes('Start Quiz'));
            if (btns.length > 0) btns[btns.length - 1].click();
        }""")
        await asyncio.sleep(2)

        # Take screenshot to verify state (with timeout protection)
        try:
            await page.screenshot(path=str(DATA_DIR / f"quiz_start_{slug}.png"), timeout=10000)
        except Exception:
            print("    (screenshot skipped)", flush=True)

        last_q_num = None
        stuck_count = 0

        for q_num in range(30):
            # Initialize for this question
            all_options_text = ""
            answer_idx = 0
            answer_indices = [0]
            is_multi_select = False

            # Get full page text first
            full_text = await page.evaluate("document.body.innerText")

            # Check if quiz complete
            if is_quiz_complete(full_text):
                result["completed"] = True
                print("    Quiz Complete!", flush=True)
                break

            # Check for Question X of Y
            q_match = re.search(r'Question (\d+) of (\d+)', full_text)
            if not q_match:
                print(f"    Q{q_num+1}: No question found", flush=True)
                if q_num == 0:
                    print(f"    Page text preview: {full_text[:300]}", flush=True)
                break

            # Get question details
            quiz_data = await page.evaluate("""() => {
                const modal = document.querySelector('#modal-root') || document.body;
                const text = modal.innerText;

                // Check for code editor (SQL question)
                const hasEditor = modal.querySelector('.cm-editor') !== null;

                // Check for textarea (free-form text response)
                const hasTextarea = modal.querySelector('textarea') !== null;

                // Check if this is a multi-select question (vs single choice)
                const isMultiSelect = text.includes('Multiple Choice') && !text.includes('Single Choice');

                // Parse question from text - get SHORT version for display
                let questionShort = '';
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i].includes('% Complete')) {
                        // Question is usually next non-empty line
                        for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
                            if (lines[j] &&
                                !lines[j].includes('Single Choice') &&
                                !lines[j].includes('Multiple Choice') &&
                                lines[j].length > 10) {
                                questionShort = lines[j];
                                break;
                            }
                        }
                        break;
                    }
                }

                // Extract FULL question text for ALL question types (MC, SQL, text)
                // This captures everything between "% Complete" and the options/input area
                let questionFull = questionShort;

                // For SQL questions, capture up to "Available Tables"
                if (hasEditor) {
                    const fullMatch = text.match(/\\d+% Complete\\s*([\\s\\S]*?)(?=Available Tables?:|$)/i);
                    if (fullMatch) {
                        questionFull = fullMatch[1]
                            .replace(/Single Choice|Multiple Choice/g, '')
                            .trim();
                        if (questionFull.length > 3000) {
                            questionFull = questionFull.substring(0, 3000);
                        }
                    }
                } else {
                    // For MC questions, capture everything between "% Complete" and the options
                    // The options are in .space-y-3 buttons, so we need to find where they start
                    // Strategy: get text up to the option container, or use a generous capture

                    // First, try to find the question container specifically
                    const questionContainer = modal.querySelector('.prose, .question-text, [class*="question"]');
                    if (questionContainer) {
                        questionFull = questionContainer.innerText.trim();
                    } else {
                        // Fallback: capture from "% Complete" to a reasonable length
                        // Look for code blocks (``` or indented code)
                        const fullMatch = text.match(/\\d+% Complete\\s*([\\s\\S]{10,2000})/);
                        if (fullMatch) {
                            let captured = fullMatch[1];
                            // Try to trim at the options if we can detect them
                            // Options usually come after a blank line following code
                            const lines = captured.split('\\n');
                            let questionLines = [];
                            let foundOptions = false;
                            for (const line of lines) {
                                // Stop if we hit what looks like an option (short line that could be an answer)
                                if (line.match(/^(Single Choice|Multiple Choice|Check Answer|\\d+ of \\d+)/i)) {
                                    continue; // Skip these lines
                                }
                                if (!foundOptions) {
                                    questionLines.push(line);
                                }
                            }
                            questionFull = questionLines.join('\\n')
                                .replace(/Single Choice|Multiple Choice/g, '')
                                .trim();
                        }
                    }
                    if (questionFull.length > 3000) {
                        questionFull = questionFull.substring(0, 3000);
                    }
                }

                // Get tables and expected columns from text
                let tables = [];
                let expectedCols = [];
                const tableMatch = text.match(/Available Tables?:\\s*([\\w.]+)/i);
                if (tableMatch) tables.push(tableMatch[1]);

                // Parse expected output columns with their data types
                const colSection = text.match(/Expected Output Columns?:([\\s\\S]*?)(?=SQL Query|Write Your|$)/i);
                if (colSection) {
                    const colLines = colSection[1].split('\\n').filter(l => l.trim());
                    colLines.forEach(line => {
                        // Match "column_name type" e.g., "sale_id integer" or "salesperson varchar"
                        const match = line.trim().match(/^([\\w_]+)\\s+([\\w()]+)/);
                        if (match) {
                            expectedCols.push({name: match[1], type: match[2].toLowerCase()});
                        }
                    });
                }

                // Get options (multiple choice) - try multiple selectors
                const options = [];

                // Try .space-y-3 first (most common)
                let optionContainer = modal.querySelector('.space-y-3');
                if (optionContainer) {
                    optionContainer.querySelectorAll('button').forEach(btn => {
                        // Try p element first, then direct text
                        const p = btn.querySelector('p');
                        const text = p ? p.innerText.trim() : btn.innerText.trim();
                        if (text && text.length > 0 && text.length < 500) {
                            options.push(text);
                        }
                    });
                }

                // If no options found, try other common containers
                if (options.length < 2) {
                    const containers = modal.querySelectorAll('[class*="option"], [class*="choice"], [class*="answer"]');
                    containers.forEach(container => {
                        const btns = container.querySelectorAll('button');
                        btns.forEach(btn => {
                            const text = btn.innerText.trim();
                            if (text && text.length > 0 && text.length < 500 && !options.includes(text)) {
                                options.push(text);
                            }
                        });
                    });
                }

                // Last resort: find all buttons that look like options (have short text, not action buttons)
                if (options.length < 2) {
                    const allButtons = modal.querySelectorAll('button');
                    allButtons.forEach(btn => {
                        const text = btn.innerText.trim();
                        // Filter out action buttons (Check Answer, Next, etc.)
                        if (text && text.length > 0 && text.length < 200 &&
                            !text.includes('Check') && !text.includes('Next') &&
                            !text.includes('Start') && !text.includes('Submit') &&
                            !options.includes(text)) {
                            options.push(text);
                        }
                    });
                }

                return { question: questionShort, questionFull, hasEditor, hasTextarea, tables, expectedCols, options, isMultiSelect };
            }""")

            question = quiz_data.get('question', '')
            question_full = quiz_data.get('questionFull', question)  # Full question with code snippets
            has_editor = quiz_data.get('hasEditor', False)
            has_textarea = quiz_data.get('hasTextarea', False)
            options = quiz_data.get('options', [])
            is_multi_select = quiz_data.get('isMultiSelect', False)

            # Check if quiz modal is still open
            modal_open = await page.evaluate("""() => {
                const modal = document.querySelector('.modal-open, [data-testid="modal-container"]');
                return modal !== null;
            }""")
            if not modal_open:
                print("    Quiz modal closed - quiz may be complete", flush=True)
                result["completed"] = True
                break

            # Get current question number from page for stuck detection
            current_q_num = None
            q_num_match = re.search(r'Question (\d+) of (\d+)', full_text)
            if q_num_match:
                current_q_num = int(q_num_match.group(1))

            # Stuck detection - use question NUMBER not text (text can be same for different Qs)
            if current_q_num is not None and current_q_num == last_q_num:
                stuck_count += 1
                if stuck_count >= 3:
                    print("    Stuck on same question - quiz may be complete", flush=True)
                    result["completed"] = True
                    break
                else:
                    print(f"    Same question #{current_q_num} detected (attempt {stuck_count}/3), waiting...", flush=True)
                    await asyncio.sleep(2)
                    continue
            else:
                stuck_count = 0
            last_q_num = current_q_num

            if has_editor:
                # SQL Writing Question - Use Claude to solve iteratively
                tables = quiz_data.get('tables', [])
                expected_cols = quiz_data.get('expectedCols', [])
                table = tables[0] if tables else "unknown_table"
                question_full = quiz_data.get('questionFull', question)  # Get full question with examples

                print(f"    Q{q_num+1}: [SQL] {question[:80]}...", flush=True)
                # Format column display
                if expected_cols and isinstance(expected_cols[0], dict):
                    col_display = ", ".join([f"{c['name']}:{c['type']}" for c in expected_cols])
                else:
                    col_display = ", ".join(expected_cols) if expected_cols else "none"
                print(f"         Table: {table}", flush=True)
                print(f"         Columns: {col_display}", flush=True)

                # STEP 1: Explore the data first by running SELECT * LIMIT 3
                sample_data = None
                if table != "unknown_table":
                    print(f"         Exploring data structure...", flush=True)
                    explore_sql = f"SELECT * FROM {table} LIMIT 3"

                    # Set the explore query in CodeMirror
                    editor_elem = await page.query_selector('.cm-editor .cm-content')
                    if editor_elem:
                        await editor_elem.click(click_count=3)
                        await asyncio.sleep(0.2)
                        await page.keyboard.type(explore_sql, delay=8)
                        await asyncio.sleep(0.3)

                        # Click Run Query to explore
                        await page.evaluate("""() => {
                            const buttons = Array.from(document.querySelectorAll('button'));
                            const btn = buttons.find(b => b.innerText.includes('Run Query'));
                            if (btn) btn.click();
                        }""")
                        await asyncio.sleep(3)

                        # Capture the sample data output
                        sample_result = await page.evaluate("""() => {
                            const modal = document.querySelector('.modal-box') || document.body;
                            let output = '';

                            // Find the query result table
                            const tables = modal.querySelectorAll('table');
                            for (const table of tables) {
                                const headers = Array.from(table.querySelectorAll('th')).map(h => h.innerText.trim());
                                // Skip quiz attempts table
                                if (headers.includes('Date') && headers.includes('Score')) continue;
                                if (headers.length > 0) {
                                    output = 'COLUMNS: ' + headers.join(' | ') + '\\n';
                                    const rows = table.querySelectorAll('tbody tr');
                                    for (let i = 0; i < Math.min(3, rows.length); i++) {
                                        const cells = Array.from(rows[i].querySelectorAll('td')).map(c => {
                                            const text = c.innerText.trim();
                                            // Truncate long JSON values but preserve structure
                                            return text.length > 200 ? text.substring(0, 200) + '...' : text;
                                        });
                                        output += 'Row ' + (i+1) + ': ' + cells.join(' | ') + '\\n';
                                    }
                                    break;
                                }
                            }
                            return output;
                        }""")

                        if sample_result:
                            sample_data = sample_result
                            print(f"         Sample: {sample_data[:100]}...", flush=True)
                        else:
                            print(f"         (no sample data captured)", flush=True)

                # Iterative solving loop - iterate on SQL ERRORS only (up to 10 attempts)
                # Once query runs without errors, submit once (can't retry after Check Answer)
                feedback = None
                solved = False
                submitted = False
                max_attempts = 10
                attempt_history = []  # Track all attempts for failure analysis

                for attempt in range(max_attempts):
                    if submitted:
                        break  # Can't retry after submitting

                    # Get SQL from Claude - use FULL question with examples + sample data
                    print(f"         Attempt {attempt + 1}/{max_attempts}: Asking Claude...", flush=True)
                    sql = solve_sql_with_claude(question_full, table, expected_cols, feedback, sample_data)

                    if not sql:
                        print(f"         Claude failed to generate SQL", flush=True)
                        # Fallback to pattern-based generation
                        sql = generate_sql(question, tables, expected_cols)
                        sql = ' '.join(sql.split())

                    print(f"         SQL: {sql[:100]}...", flush=True)

                    # Set SQL in CodeMirror
                    editor_elem = await page.query_selector('.cm-editor .cm-content')
                    if editor_elem:
                        await editor_elem.click(click_count=3)
                        await asyncio.sleep(0.2)
                        await page.keyboard.type(sql, delay=8)
                        await asyncio.sleep(0.3)
                    else:
                        print("         Editor not found!", flush=True)
                        break

                    await asyncio.sleep(0.5)

                    # Click Run Query
                    await page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const btn = buttons.find(b => b.innerText.includes('Run Query'));
                        if (btn) btn.click();
                    }""")
                    await asyncio.sleep(4)

                    # Scroll to see results
                    await page.evaluate("""() => {
                        const modal = document.querySelector('.modal-box');
                        if (modal) modal.scrollTop = modal.scrollHeight;
                    }""")
                    await asyncio.sleep(1)

                    # Capture query results - look for success/error feedback from the page
                    page_feedback = await page.evaluate("""() => {
                        const modal = document.querySelector('.modal-box') || document.querySelector('[role="dialog"]') || document.body;
                        const modalText = modal.innerText;
                        const modalHtml = modal.innerHTML;

                        // Look for explicit success indicators
                        const hasSuccess = modalText.includes('rows returned') ||
                                          modalText.includes('Query executed') ||
                                          modalHtml.includes('text-success') ||
                                          modalHtml.includes('bg-success');

                        // Look for explicit error indicators
                        const hasError = modalHtml.includes('text-error') ||
                                        modalHtml.includes('bg-error') ||
                                        modalHtml.includes('text-red') ||
                                        modalText.toLowerCase().includes('error:') ||
                                        modalText.toLowerCase().includes('syntax error') ||
                                        modalText.toLowerCase().includes('parse error') ||
                                        modalText.toLowerCase().includes('not found') ||
                                        modalText.toLowerCase().includes('cannot be applied');

                        // Extract error message - look for various patterns
                        let errorText = '';
                        // Try to find error in red/error styled elements
                        const errorEls = modal.querySelectorAll('.text-error, .text-red-500, .text-red-600, [class*="error"]');
                        for (const el of errorEls) {
                            if (el.innerText.trim().length > 5) {
                                errorText = el.innerText.trim().substring(0, 500);
                                break;
                            }
                        }
                        // Fallback to regex
                        if (!errorText) {
                            const errorMatch = modalText.match(/(?:Error|error)[:\\s]+([^\\n]+)/i);
                            if (errorMatch) errorText = errorMatch[1].trim();
                        }
                        // Last resort - look for common SQL error patterns
                        if (!errorText && hasError) {
                            const patterns = [
                                /line \\d+:\\d+: (.+)/i,
                                /column '([^']+)' cannot/i,
                                /table '([^']+)' not found/i,
                                /function '([^']+)' not found/i,
                            ];
                            for (const p of patterns) {
                                const m = modalText.match(p);
                                if (m) { errorText = m[0]; break; }
                            }
                        }

                        // Get row count if shown
                        const rowsMatch = modalText.match(/(\\d+)\\s*rows? returned/i);
                        const rowsReturned = rowsMatch ? parseInt(rowsMatch[1]) : -1;

                        // Capture actual query output table
                        let outputSummary = '';
                        const tables = modal.querySelectorAll('table');
                        for (const table of tables) {
                            const headers = Array.from(table.querySelectorAll('th')).map(h => h.innerText.trim());
                            // Skip quiz attempts table
                            if (headers.includes('Date') && headers.includes('Score')) continue;
                            if (headers.length > 0) {
                                outputSummary = 'COLUMNS: ' + headers.join(', ') + '\\n';
                                const rows = table.querySelectorAll('tbody tr');
                                outputSummary += 'DATA (' + rows.length + ' rows):\\n';
                                for (let i = 0; i < Math.min(5, rows.length); i++) {
                                    const cells = Array.from(rows[i].querySelectorAll('td')).map(c => c.innerText.trim() || '(empty)');
                                    outputSummary += '  Row ' + (i+1) + ': ' + cells.join(' | ') + '\\n';
                                }
                                break;
                            }
                        }

                        // Check if Check Answer button is enabled
                        const checkAnswerEnabled = Array.from(document.querySelectorAll('button'))
                            .some(b => b.innerText.includes('Check Answer') && !b.disabled);

                        return {
                            hasSuccess: hasSuccess,
                            hasError: hasError,
                            errorText: errorText,
                            rowsReturned: rowsReturned,
                            outputSummary: outputSummary,
                            checkAnswerEnabled: checkAnswerEnabled,
                            // For debugging - first 500 chars of modal text
                            debugText: modalText.substring(0, 500)
                        };
                    }""")

                    # Check if query succeeded or failed
                    has_error = page_feedback.get('hasError', False)
                    has_success = page_feedback.get('hasSuccess', False)
                    error_text = page_feedback.get('errorText', '')
                    rows_returned = page_feedback.get('rowsReturned', -1)

                    if has_error:
                        # Query failed - pass FULL error message AND output to Claude
                        output_summary = page_feedback.get('outputSummary', '')
                        debug_text = page_feedback.get('debugText', '')[:300]

                        feedback_parts = [f"VALIDATION ERROR: {error_text}" if error_text else "Query validation failed."]
                        if output_summary:
                            feedback_parts.append(f"\nYOUR QUERY OUTPUT:\n{output_summary}")
                        feedback_parts.append(f"\nFix the query based on this feedback. Previous query: {sql}")
                        feedback = "\n".join(feedback_parts)

                        # Track this attempt for failure analysis
                        attempt_history.append({
                            "attempt": attempt + 1,
                            "sql": sql,
                            "error": error_text or "validation failed",
                            "output": output_summary[:500] if output_summary else ""
                        })

                        print(f"         Error: {error_text[:80] if error_text else 'validation failed'}, retrying...", flush=True)
                        continue
                    elif has_success or rows_returned >= 0:
                        # Query succeeded - submit
                        print(f"         Query succeeded ({rows_returned} rows), submitting...", flush=True)
                    else:
                        # Unclear - check if Check Answer is enabled
                        if not page_feedback['checkAnswerEnabled']:
                            # Something went wrong, iterate
                            debug = page_feedback.get('debugText', '')[:200]
                            feedback = f"Query may have failed (Check Answer not enabled). Debug: {debug}. Query was: {sql}"

                            # Track this attempt
                            attempt_history.append({
                                "attempt": attempt + 1,
                                "sql": sql,
                                "error": "Check Answer not enabled",
                                "output": page_feedback.get('outputSummary', '')[:500]
                            })

                            print(f"         Check Answer not enabled, retrying...", flush=True)
                            continue
                        else:
                            print(f"         Submitting...", flush=True)

                    # Output looks OK or max attempts - submit the answer
                    if page_feedback['checkAnswerEnabled']:
                        print(f"         Submitting answer...", flush=True)

                        check_result = await page.evaluate("""() => {
                            const buttons = Array.from(document.querySelectorAll('button'));
                            const checkBtn = buttons.find(b => b.innerText.includes('Check Answer'));
                            if (checkBtn && !checkBtn.disabled) {
                                checkBtn.scrollIntoView({ behavior: 'instant', block: 'center' });
                                checkBtn.click();
                                return 'clicked';
                            }
                            return 'failed';
                        }""")

                        submitted = True
                        await asyncio.sleep(2)

                        # Check if correct
                        result_check = await page.evaluate("""() => {
                            const text = document.body.innerText;
                            return {
                                correct: text.includes('Correct!') || text.includes('Output matches'),
                                incorrect: text.includes('Incorrect') || text.includes('does not match')
                            };
                        }""")

                        if result_check['correct']:
                            print(f"         ✓ CORRECT!", flush=True)
                            result["score"] += 1
                            solved = True
                        else:
                            print(f"         ✗ Incorrect (can't retry after submission)", flush=True)
                        break  # Exit loop after submission either way
                    else:
                        feedback = f"Check Answer button not enabled. Query may have failed silently. Query was: {sql}"
                        print(f"         Check Answer not enabled, retrying...", flush=True)

                if not submitted:
                    print(f"         Failed to submit after {max_attempts} attempts", flush=True)

                    # Capture detailed info about this failed question for later analysis
                    failed_info = {
                        "quiz_slug": slug,
                        "quiz_title": title,
                        "question_number": q_num + 1,
                        "question_text": question,
                        "table": table,
                        "expected_columns": expected_cols,
                        "attempts": attempt_history,
                        "page_snapshot": ""
                    }

                    # Capture page state
                    try:
                        page_text = await page.evaluate("document.body.innerText")
                        failed_info["page_snapshot"] = page_text[:2000]
                    except:
                        pass

                    # Save to failed_quizzes.json for later review
                    failed_file = DATA_DIR / "failed_quizzes.json"
                    try:
                        if failed_file.exists():
                            with open(failed_file) as f:
                                failed_data = json.load(f)
                        else:
                            failed_data = []
                        failed_data.append(failed_info)
                        with open(failed_file, "w") as f:
                            json.dump(failed_data, f, indent=2)
                        print(f"         Saved failure details to {failed_file}", flush=True)
                    except Exception as e:
                        print(f"         Could not save failure details: {e}", flush=True)

                # Check for quiz completion before navigating
                completion_check = await page.evaluate("""() => {
                    const text = document.body.innerText;
                    return {
                        complete: text.includes('Quiz Complete') || text.includes('You passed') || text.includes('100% Complete'),
                        lessonComplete: text.includes('Lesson Completed')
                    };
                }""")
                if completion_check['complete'] or completion_check['lessonComplete']:
                    result["completed"] = True
                    print("    Quiz Complete!", flush=True)
                    break

                result["questions"].append({"q": question[:150], "a": sql[:200] if sql else "failed", "type": "sql", "solved": solved})

                # Navigate to next question
                await asyncio.sleep(0.5)
                next_clicked = await page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    let btn = buttons.find(b => b.innerText.includes('Next Question'));
                    if (!btn) btn = buttons.find(b => b.innerText.trim() === 'Next');
                    if (!btn) btn = buttons.find(b => b.innerText.includes('Next'));
                    if (btn && !btn.disabled) {
                        btn.click();
                        return btn.innerText.trim();
                    }
                    return null;
                }""")
                if next_clicked:
                    print(f"         → {next_clicked[:20]}", flush=True)
                await asyncio.sleep(2)

                # Check for quiz completion
                new_text = await page.evaluate("document.body.innerText")
                if is_quiz_complete(new_text, check_progress=True):
                    result["completed"] = True
                    print("    Quiz Complete!", flush=True)
                    break

                continue  # Skip the rest of the loop for SQL questions

            elif has_textarea:
                # Free-form text response question (design questions, etc.)
                print(f"    Q{q_num+1}: [TEXT] {question[:80]}...", flush=True)

                # Get the full question text from the modal
                full_question = await page.evaluate("""() => {
                    const modal = document.querySelector('.modal-box') || document.body;
                    const text = modal.innerText;
                    // Extract everything between "% Complete" and "Your Response"
                    const match = text.match(/\\d+% Complete\\s*([\\s\\S]*?)Your Response/);
                    return match ? match[1].trim() : text.substring(0, 500);
                }""")

                # Iterative solving loop for text responses
                feedback = None
                submitted = False
                solved = False
                max_attempts = 3  # Text responses typically need fewer iterations

                for attempt in range(max_attempts):
                    if submitted:
                        break

                    print(f"         Attempt {attempt + 1}/{max_attempts}: Asking Claude...", flush=True)
                    response = solve_text_response_with_claude(full_question, feedback)

                    if not response:
                        print(f"         Claude failed to generate response", flush=True)
                        continue

                    print(f"         Response: {response[:100]}...", flush=True)

                    # Type response into textarea
                    textarea = await page.query_selector('textarea')
                    if textarea:
                        await textarea.click()
                        await asyncio.sleep(0.2)
                        # Clear existing content
                        await page.keyboard.press('Control+a')
                        await asyncio.sleep(0.1)
                        await page.keyboard.type(response, delay=5)
                        await asyncio.sleep(0.5)
                    else:
                        print("         Textarea not found!", flush=True)
                        break

                    # Click Check Answer
                    await page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const btn = buttons.find(b => b.innerText.includes('Check Answer'));
                        if (btn && !btn.disabled) btn.click();
                    }""")
                    await asyncio.sleep(3)

                    # Check result
                    result_text = await page.evaluate("""() => {
                        const modal = document.querySelector('.modal-box') || document.body;
                        return modal.innerText;
                    }""")

                    if "Correct" in result_text or "Well done" in result_text or "good" in result_text.lower():
                        print(f"         ✓ CORRECT!", flush=True)
                        solved = True
                        submitted = True
                    elif "Incorrect" in result_text or "incorrect" in result_text.lower() or "try again" in result_text.lower():
                        # Extract feedback if available
                        feedback_match = re.search(r'(feedback|suggestion|hint)[:\s]*([^\n]+)', result_text, re.IGNORECASE)
                        if feedback_match:
                            feedback = feedback_match.group(2)
                        else:
                            feedback = "Your answer was marked incorrect. Please provide more detail or a different approach."
                        print(f"         ✗ Incorrect", flush=True)
                        submitted = True  # Can't retry after Check Answer
                    else:
                        # Check for any positive indicator
                        if any(x in result_text.lower() for x in ['passed', 'success', 'accepted', 'great']):
                            print(f"         ✓ Accepted!", flush=True)
                            solved = True
                        else:
                            print(f"         Result unclear, assuming submitted", flush=True)
                        submitted = True

                if solved:
                    result["questions"].append({"q": question[:150], "a": response[:200] if response else "", "type": "text", "correct": True})
                else:
                    result["questions"].append({"q": question[:150], "a": response[:200] if response else "", "type": "text", "correct": False})

                # Click Next Question
                await page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const btn = buttons.find(b => b.innerText.includes('Next'));
                    if (btn) btn.click();
                }""")
                await asyncio.sleep(2)

                continue  # Skip the rest of the loop for text questions

            elif len(options) >= 2:
                # Multiple Choice - Use Claude to answer with FULL question (includes code snippets)
                select_type = "[MULTI]" if is_multi_select else "[SINGLE]"
                print(f"    Q{q_num+1}: {select_type} {question[:40]}...", flush=True)
                print(f"         Asking Claude for MC answer...", flush=True)
                # Use question_full to include any code snippets in the question
                answer_indices = solve_mc_with_claude(question_full, options, multi_select=is_multi_select)
                answer_idx = answer_indices[0] if answer_indices else 0  # For compatibility

                # Format selected answers for display
                selected_letters = [chr(65+i) for i in answer_indices]
                selected_texts = [options[i][:30] if i < len(options) else "?" for i in answer_indices]
                print(f"         Selected: {', '.join(selected_letters)} - {selected_texts[0]}{'...' if len(selected_texts) > 1 else ''}", flush=True)

                # Store all options for debugging wrong answers
                all_options_text = "\n".join([f"           {chr(65+i)}. {opt[:60]}" for i, opt in enumerate(options)])

                # Click option(s) - for multi-select, click all selected options
                for idx in answer_indices:
                    await page.evaluate(f"""(idx) => {{
                        const modal = document.querySelector('#modal-root') || document.body;
                        const container = modal.querySelector('.space-y-3');
                        if (container) {{
                            const buttons = container.querySelectorAll('button');
                            if (buttons[idx]) buttons[idx].click();
                        }}
                    }}""", idx)
                    await asyncio.sleep(0.2)  # Small delay between clicks for multi-select

                # Save full question for debugging (truncate for storage but keep more)
                answer_text = ", ".join([options[i][:50] if i < len(options) else "?" for i in answer_indices])
                result["questions"].append({"q": question_full[:500], "a": answer_text[:100], "type": "choice", "multi": is_multi_select})
            else:
                print(f"    Q{q_num+1}: Parse error (no options, no editor)", flush=True)
                break

            await asyncio.sleep(0.5)

            # Click Check Answer - scroll to it first and click
            check_clicked = await page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const checkBtn = buttons.find(b => b.innerText.includes('Check Answer'));
                if (checkBtn) {
                    // Scroll the button into view
                    checkBtn.scrollIntoView({ behavior: 'instant', block: 'center' });
                    // Check if it's enabled
                    if (!checkBtn.disabled) {
                        checkBtn.click();
                        return 'clicked';
                    }
                    return 'disabled';
                }
                return 'not_found';
            }""")
            print(f"         Check Answer: {check_clicked}", flush=True)

            if check_clicked == 'disabled':
                # Wait a bit more for it to become enabled
                await asyncio.sleep(2)
                check_clicked = await page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const checkBtn = buttons.find(b => b.innerText.includes('Check Answer'));
                    if (checkBtn && !checkBtn.disabled) {
                        checkBtn.click();
                        return 'clicked_retry';
                    }
                    return 'still_disabled';
                }""")
                print(f"         Check Answer retry: {check_clicked}", flush=True)

            await asyncio.sleep(2.5)

            # Get available buttons for debugging
            buttons_info = await page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                return buttons.filter(b => b.offsetParent !== null).map(b => b.innerText.trim().substring(0, 25)).slice(0, 10);
            }""")
            print(f"         Buttons: {buttons_info[:5]}", flush=True)

            # Check result - look for result in modal before it closes
            await asyncio.sleep(0.5)
            result_info = await page.evaluate("""() => {
                const text = document.body.innerText;
                return {
                    correct: text.includes('Correct!') || (text.includes('Output matches') && !text.includes('does not match')),
                    incorrect: text.includes('Incorrect') || text.includes('does not match'),
                    complete: text.includes('Quiz Complete') || text.includes('You passed')
                };
            }""")

            if result_info['complete']:
                result["completed"] = True
                print("    Quiz Complete!", flush=True)
                break

            if result_info['correct']:
                result["score"] += 1
                print(f"         ✓ Correct!", flush=True)
            elif result_info['incorrect']:
                print(f"         ✗ Incorrect", flush=True)
                # Log full question and all options for wrong answers
                print(f"         --- WRONG ANSWER DEBUG ---", flush=True)
                print(f"         Multi-select: {is_multi_select}", flush=True)
                print(f"         Question: {question_full[:200]}", flush=True)
                print(f"         All options:", flush=True)
                print(all_options_text, flush=True)
                chosen = ", ".join([chr(65+i) for i in answer_indices])
                print(f"         We chose: {chosen}", flush=True)
                print(f"         --------------------------", flush=True)
            else:
                print(f"         ? No result detected", flush=True)

            # Click Next - look for it immediately while modal might still be open
            await asyncio.sleep(0.5)
            next_clicked = await page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                // Try "Next Question" first (common in quiz modals)
                let btn = buttons.find(b => b.innerText.includes('Next Question'));
                // Then exact "Next"
                if (!btn) btn = buttons.find(b => b.innerText.trim() === 'Next');
                // Then contains "Next"
                if (!btn) btn = buttons.find(b => b.innerText.includes('Next'));
                // Then Continue
                if (!btn) btn = buttons.find(b => b.innerText.includes('Continue'));
                if (btn && !btn.disabled) {
                    btn.scrollIntoView({ behavior: 'instant', block: 'center' });
                    btn.click();
                    return btn.innerText.trim();
                }
                return null;
            }""")
            if next_clicked:
                print(f"         → Clicked: {next_clicked[:20]}", flush=True)

            # Wait for page to load next question (this is critical!)
            await asyncio.sleep(5)

            # Wait for question text to change (indicates new question loaded)
            for wait_attempt in range(5):
                new_text = await page.evaluate("document.body.innerText")
                # Check if quiz is complete
                if is_quiz_complete(new_text, check_progress=True):
                    result["completed"] = True
                    print("    Quiz Complete!", flush=True)
                    break
                # Check if question changed by looking for different question number
                q_match = re.search(r'Question (\d+) of (\d+)', new_text)
                if q_match:
                    new_q_num = int(q_match.group(1))
                    if new_q_num > q_num + 1:  # Question number increased
                        break
                await asyncio.sleep(1)

            if result.get("completed"):
                break

        # Summary
        total = len(result["questions"])
        if total > 0:
            pct = (result["score"] / total) * 100
            status = "PASSED" if pct >= 70 else f"{pct:.0f}%"
            print(f"    → {result['score']}/{total} ({status})", flush=True)
            if pct >= 70:
                result["completed"] = True

    except Exception as e:
        print(f"    ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()

    return result


async def main():
    """Solve every quiz via the Claude CLI, skipping ones already at 100%.

    ``solve_quiz`` detects an already-perfect quiz and returns early, so this is
    safe to re-run: completed quizzes are skipped and only unfinished ones are
    attempted.
    """
    results = {"timestamp": datetime.now().isoformat(), "quizzes": []}

    async with async_playwright() as p:
        print("Connecting to Chrome...", flush=True)
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = await context.new_page()

        for slug, title in ALL_QUIZZES:
            try:
                result = await solve_quiz(page, slug, title)
                results["quizzes"].append(result)
            except Exception as e:
                if "closed" in str(e).lower():
                    # Browser/page closed - try to reconnect
                    print(f"    Connection lost, reconnecting...", flush=True)
                    try:
                        browser = await p.chromium.connect_over_cdp(CDP_URL)
                        context = browser.contexts[0]
                        page = await context.new_page()
                        # Retry this quiz
                        result = await solve_quiz(page, slug, title)
                        results["quizzes"].append(result)
                    except Exception as e2:
                        print(f"    Reconnect failed: {e2}", flush=True)
                        results["quizzes"].append({"slug": slug, "title": title, "error": str(e2)})
                else:
                    print(f"    ERROR: {e}", flush=True)
                    results["quizzes"].append({"slug": slug, "title": title, "error": str(e)})

            # Save progress
            with open(DATA_DIR / "v2_progress.json", "w") as f:
                json.dump(results, f, indent=2)

        try:
            await page.close()
        except:
            pass

    # Summary
    passed = sum(1 for r in results["quizzes"] if r.get("completed", False))
    total_q = sum(len(r.get("questions", [])) for r in results["quizzes"])
    total_c = sum(r.get("score", 0) for r in results["quizzes"])
    pct = (total_c / total_q * 100) if total_q > 0 else 0
    print(f"\n{'='*50}", flush=True)
    print(f"COMPLETE: {passed}/{len(ALL_QUIZZES)} passed", flush=True)
    print(f"Questions: {total_c}/{total_q} correct ({pct:.0f}%)", flush=True)


async def check_quiz_status(page, slug: str, title: str) -> dict:
    """Check quiz completion status without taking the quiz."""
    result = {"slug": slug, "title": title, "status": "unknown", "score": None}

    try:
        url = lesson_url(slug)
        await page.goto(url, wait_until='networkidle', timeout=30000)

        if "/sign-in" in page.url:
            result["status"] = "not_logged_in"
            return result

        await asyncio.sleep(1)

        # Click Quiz tab first
        await page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const btn = buttons.find(b => b.innerText.trim() === 'Quiz');
            if (btn) btn.click();
        }""")
        await asyncio.sleep(1.5)

        # Read the page text and classify it. The score regex and the
        # perfect/incomplete/completed/not_started/unknown decision live in
        # quiz_status (pure, tested) — this used to be a third inlined copy of the
        # score regex.
        page_text = await page.evaluate("document.body.innerText")
        status, score = classify_status(page_text)
        result["status"] = status
        if score is not None:
            result["score"] = score

    except Exception as e:
        result["status"] = f"error: {str(e)[:50]}"

    return result


async def status_check():
    """Check status of all quizzes without taking them."""
    print("Quiz Status Check", flush=True)
    print("="*60, flush=True)

    async with async_playwright() as p:
        print("Connecting to Chrome...", flush=True)
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = await context.new_page()

        # Group quizzes by week — straight from the shared curriculum, so this
        # stays correct even if the quiz list changes (no magic-number slices).
        all_results = {}
        for week_name, quizzes in CURRICULUM.items():
            print(f"\n{week_name}", flush=True)
            print("-"*40, flush=True)
            week_results = []
            for slug, title in quizzes:
                result = await check_quiz_status(page, slug, title)
                week_results.append(result)

                # Display status
                status = result["status"]
                score = result.get("score", "")
                if status == "perfect":
                    print(f"  ✓ {title}: {score}", flush=True)
                elif status == "completed" or status == "incomplete":
                    print(f"  ○ {title}: {score or status}", flush=True)
                elif status == "not_started":
                    print(f"  - {title}: Not started", flush=True)
                else:
                    print(f"  ? {title}: {status}", flush=True)

            all_results[week_name] = week_results

        # Summary
        print(f"\n{'='*60}", flush=True)
        print("SUMMARY", flush=True)
        print("-"*40, flush=True)

        total_perfect = 0
        total_incomplete = 0
        total_not_started = 0

        for week_name, results in all_results.items():
            perfect = sum(1 for r in results if r["status"] == "perfect")
            incomplete = sum(1 for r in results if r["status"] in ["incomplete", "completed"])
            not_started = sum(1 for r in results if r["status"] == "not_started")
            total = len(results)

            if perfect == total:
                print(f"  ✓ {week_name}: {perfect}/{total} perfect", flush=True)
            else:
                print(f"  ○ {week_name}: {perfect}/{total} perfect, {incomplete} incomplete, {not_started} not started", flush=True)

            total_perfect += perfect
            total_incomplete += incomplete
            total_not_started += not_started

        total_quizzes = len(ALL_QUIZZES)
        print(f"\nOVERALL: {total_perfect}/{total_quizzes} perfect ({total_perfect/total_quizzes*100:.0f}%)", flush=True)

        try:
            await page.close()
        except:
            pass

    return all_results


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print("Running status check...", flush=True)
        asyncio.run(status_check())
    else:
        print("Enhanced Quiz Runner v2", flush=True)
        print("="*40, flush=True)
        asyncio.run(main())
