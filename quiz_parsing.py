"""Pure parsers for the Claude CLI's quiz responses.

``run_quizzes_v2.py`` shells out to the ``claude`` CLI to answer multiple-choice,
SQL, and free-text questions, then has to pull a usable answer out of the model's
raw text. That extraction is pure string/regex logic with real edge cases
(multi-select de-duplication, stray letters, markdown SQL fences, preamble
phrasing) — but it used to live inside the subprocess-calling functions where it
could not be unit-tested.

It now lives here, mirroring ``quiz_heuristics`` and ``quiz_sql``: no network,
browser, or CLI, so it is covered directly by ``tests/test_quiz_parsing.py``.
"""
import re
import string
from typing import List, Optional

# A SQL answer is only accepted if it starts with one of these statements.
SQL_KEYWORDS = ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")


def parse_mc_answer(response: str, num_options: int, multi_select: bool = False) -> List[int]:
    """Parse the chosen option index/indices out of Claude's MC response.

    Looks for letters inside an ``<answer>...</answer>`` block first, then falls
    back to standalone capital letters anywhere in the response.

    Args:
        response: Claude's raw text.
        num_options: How many options the question had (caps the valid letters to
            ``A..`` and bounds the returned indices).
        multi_select: If true, return every distinct selected index in order;
            otherwise return a single-element list.

    Returns:
        0-based indices into the option list. Always non-empty: falls back to
        ``[0]`` when nothing usable is found.
    """
    # Valid answer letters for this question, e.g. "ABCD" for 4 options. Uses the
    # full alphabet (not a hard-coded "ABCD") so questions with five or more
    # options stay recognizable — matching quiz_prompts' generalized lettering.
    valid_chars = string.ascii_uppercase[:num_options]

    # Prefer an explicit <answer>...</answer> block.
    answer_match = re.search(r'<answer>\s*([A-Za-z,\s]+)\s*</answer>', response)
    if answer_match:
        answer_text = answer_match.group(1).upper()
        letters = [c for c in answer_text if c in valid_chars]
        if letters:
            indices = [ord(c) - ord('A') for c in letters if ord(c) - ord('A') < num_options]
            if indices:
                return indices if multi_select else [indices[0]]

    # Fallback: standalone capital letters anywhere in the response.
    response_upper = response.upper()
    letters_found = re.findall(rf'\b([{valid_chars}])\b', response_upper) if valid_chars else []
    if letters_found:
        if multi_select:
            # De-duplicate while preserving first-seen order.
            seen = set()
            unique_letters = [x for x in letters_found if not (x in seen or seen.add(x))]
            indices = [ord(c) - ord('A') for c in unique_letters if ord(c) - ord('A') < num_options]
            if indices:
                return indices
        else:
            # Single-select: trust the last letter mentioned (often the conclusion).
            letter = letters_found[-1]
            idx = ord(letter) - ord('A')
            if idx < num_options:
                return [idx]

    return [0]


def extract_sql(raw: str) -> Optional[str]:
    """Pull a single-line SQL statement out of Claude's raw response.

    Strips a markdown ```` ```sql ```` fence (or any code fence), otherwise grabs
    from the first SQL keyword onward, collapses all whitespace to single spaces,
    and validates the result begins with a SQL keyword.

    Returns the cleaned one-line SQL, or ``None`` if no usable SQL is found.
    """
    sql = raw.strip()

    # Extract SQL from a ```sql ... ``` code block if present.
    code_block_match = re.search(r'```sql\s*(.*?)\s*```', sql, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        sql = code_block_match.group(1)
    else:
        # Otherwise grab from the first SQL keyword to the end.
        sql_match = re.search(r'((?:SELECT|WITH|INSERT|UPDATE|DELETE)\b.*)', sql, re.DOTALL | re.IGNORECASE)
        if sql_match:
            sql = sql_match.group(1)

    # Remove any remaining code-fence markers.
    sql = re.sub(r'^```sql\s*', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'^```\s*', '', sql)
    sql = re.sub(r'\s*```$', '', sql)
    sql = sql.strip()

    # Flatten to a single line.
    sql = ' '.join(sql.split())

    if sql and sql.upper().startswith(SQL_KEYWORDS):
        return sql
    return None


def clean_text_response(response: str) -> str:
    """Strip a leading ``Here is`` / ``My answer:`` / ``Response:`` preamble.

    Free-text answers occasionally arrive with conversational framing; the grader
    wants just the answer.
    """
    return re.sub(r'^(Here is |My answer:|Response:)\s*', '', response, flags=re.IGNORECASE)
