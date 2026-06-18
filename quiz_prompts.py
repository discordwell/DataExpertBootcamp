"""Pure builders for the Claude CLI prompts used by ``run_quizzes_v2.py``.

The v2 runner shells out to the ``claude`` CLI to answer multiple-choice, SQL, and
free-text questions. Each ``solve_*_with_claude`` function used to *construct* its
prompt inline — formatting the options with letters, choosing the single- vs
multi-select instructions, normalizing the expected SQL columns, and stitching in
the optional research-context / feedback / sample-data sections — right next to the
``subprocess.run`` call, where none of that string logic could be unit-tested.

The construction is pure (no network, browser, or CLI), so it now lives here,
mirroring ``quiz_parsing`` (which already owns the *parsing* half of each
``solve_*`` function). The runner is left as a thin "build prompt -> call CLI ->
parse response" wrapper, and the prompt text is covered by
``tests/test_quiz_prompts.py``.

Splitting prompt-building out also let us fix a latent bug: the option-letter logic
silently capped at ``A``-``D``, so a question with five or more options could never
have its later options offered (or recognized — see ``quiz_parsing.parse_mc_answer``).
The helpers here generalize cleanly to any option count while producing byte-for-byte
identical text for the 2-, 3-, and 4-option questions the bootcamp actually uses.
"""
import string
from typing import List, Optional, Tuple, Union

# The DOM parser yields columns as ``{"name": ..., "type": ...}`` dicts; older
# callers pass plain name strings. The SQL prompt needs both a typed spec and a
# bare name, so it accepts either shape (mirrors ``quiz_sql.Column``).
Column = Union[str, dict]


def option_letters(num_options: int) -> List[str]:
    """Return the answer letters ``['A', 'B', ...]`` for ``num_options`` options.

    Generalizes the old hard-coded ``chr(65 + i)`` / ``"ABCD"`` handling so a
    question with more than four options is lettered correctly. Uses the same
    ``string.ascii_uppercase`` slice as ``quiz_parsing.parse_mc_answer``, so the
    letters offered in the prompt are exactly the letters the parser can recognize
    (both stop at ``Z`` — 26 options, well beyond any real quiz).
    """
    return list(string.ascii_uppercase[:num_options])


def format_options(options: List[str]) -> str:
    """Format options as ``"A. <opt>\\nB. <opt>\\n..."`` for the MC prompt."""
    letters = option_letters(len(options))
    return "\n".join(f"{letter}. {opt}" for letter, opt in zip(letters, options))


def valid_letters_phrase(num_options: int) -> str:
    """Human-readable list of the valid answer letters, e.g. ``"A, B, or C"``.

    Preserves the original phrasing exactly for the realistic range — ``"A or B"``
    for two options, ``"A, B, or C"`` for three, and ``"A, B, C, or D"`` for four
    (and, as before, for the degenerate 0/1-option cases). Five or more options
    used to *also* render as ``"A, B, C, or D"`` (the latent bug); they now extend
    correctly to ``"A, B, C, D, or E"`` and beyond.
    """
    if num_options == 2:
        return "A or B"
    if num_options == 3:
        return "A, B, or C"
    if num_options <= 4:
        return "A, B, C, or D"
    letters = option_letters(num_options)
    return ", ".join(letters[:-1]) + ", or " + letters[-1]


def build_mc_prompt(
    question: str,
    options: List[str],
    research_context: str = "",
    multi_select: bool = False,
) -> str:
    """Build the multiple-choice prompt for the Claude CLI.

    ``research_context`` is the contents of ``data/quiz_research.md`` (the runner
    reads the file; this stays pure). ``multi_select`` switches the answer-format
    and select instructions between single- and multi-answer phrasing.
    """
    options_text = format_options(options)
    valid_letters = valid_letters_phrase(len(options))

    if multi_select:
        answer_instruction = f"[One or more letters, comma-separated if multiple: {valid_letters}]"
        select_instruction = "This is a MULTI-SELECT question. You may need to select MORE THAN ONE answer. Select ALL answers that are correct."
    else:
        answer_instruction = f"[Single letter only: {valid_letters}]"
        select_instruction = "This is a SINGLE-SELECT question. Choose the ONE best answer."

    return f"""You are answering a multiple choice question from a data engineering bootcamp quiz.

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


def build_text_prompt(question: str, feedback: Optional[str] = None) -> str:
    """Build the free-text (design/interview) response prompt for the Claude CLI."""
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

    return "\n".join(prompt_parts)


def normalize_sql_columns(expected_cols: List[Column]) -> Tuple[List[str], List[str]]:
    """Split the expected columns into ``(specs, names)`` for the SQL prompt.

    ``expected_cols`` may be ``{"name", "type"}`` dicts (the live DOM shape) or
    plain name strings. For dicts, ``specs`` are ``"name (type)"`` and ``names`` are
    the bare names; for strings both are the strings as-is.
    """
    if expected_cols and isinstance(expected_cols[0], dict):
        col_specs = [f"{c['name']} ({c['type']})" for c in expected_cols]
        col_names = [c["name"] for c in expected_cols]
    else:
        # Plain list of column names (or empty): spec and name are the same.
        col_specs = list(expected_cols or [])
        col_names = list(expected_cols or [])
    return col_specs, col_names


def build_sql_prompt(
    question: str,
    table: str,
    expected_cols: List[Column],
    feedback: Optional[str] = None,
    sample_data: Optional[str] = None,
) -> str:
    """Build the SQL-writing prompt (Trino/Presto) for the Claude CLI.

    Includes the optional ``sample_data`` (``SELECT * LIMIT 3`` output) and
    ``feedback`` (previous-attempt grader error) sections when provided, and lists
    the expected output columns in order with their types.
    """
    col_specs, col_names = normalize_sql_columns(expected_cols)

    prompt_parts = [
        "You are solving a SQL quiz question. The database uses Trino/Presto SQL syntax.",
        "",
        f"**Question:** {question}",
        "",
        f"**Available Table:** {table}",
        "",
    ]

    # Sample data helps Claude understand the actual table structure.
    if sample_data:
        prompt_parts.extend([
            "**Sample Data from Table (SELECT * LIMIT 3):**",
            "```",
            sample_data,
            "```",
            "",
        ])

    prompt_parts.append("**Expected Output Columns (in exact order with data types):**")

    # One column per line for clarity.
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

    return "\n".join(prompt_parts)
