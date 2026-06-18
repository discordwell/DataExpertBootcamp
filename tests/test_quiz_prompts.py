"""Tests for the pure Claude-prompt builders in ``quiz_prompts``.

These functions used to be inlined inside the ``solve_*_with_claude`` functions in
``run_quizzes_v2.py``, right next to the ``subprocess.run`` call, so the prompt text
(option lettering, single/multi-select wording, SQL column normalization, and the
optional research-context / feedback / sample-data sections) could not be tested
without the CLI. Pulling them into a pure module — mirroring ``quiz_parsing``, which
owns the parsing half — makes all of that unit-testable here.

The builders were verified to reproduce the original inline f-strings byte-for-byte
over 90k randomized inputs for the realistic (<=4) option range before the runner was
rewired; these tests pin the resulting behavior and guard the >=5-option fix.
"""
import pytest

from quiz_prompts import (
    build_mc_prompt,
    build_sql_prompt,
    build_text_prompt,
    format_options,
    normalize_sql_columns,
    option_letters,
    valid_letters_phrase,
)


# ---------------------------------------------------------------------------
# option_letters / format_options
# ---------------------------------------------------------------------------

class TestOptionLetters:
    def test_basic_counts(self):
        assert option_letters(0) == []
        assert option_letters(1) == ["A"]
        assert option_letters(4) == ["A", "B", "C", "D"]

    def test_beyond_four(self):
        # The old code capped at A-D; lettering must keep going.
        assert option_letters(6) == ["A", "B", "C", "D", "E", "F"]

    def test_format_options_letters_each_line(self):
        assert format_options(["red", "green", "blue"]) == "A. red\nB. green\nC. blue"

    def test_format_options_empty(self):
        assert format_options([]) == ""

    def test_format_options_preserves_text_verbatim(self):
        # Option text (including punctuation) is passed through unchanged.
        assert format_options(["All of the above"]) == "A. All of the above"


# ---------------------------------------------------------------------------
# valid_letters_phrase
# ---------------------------------------------------------------------------

class TestValidLettersPhrase:
    @pytest.mark.parametrize("n,expected", [
        (0, "A, B, C, or D"),   # degenerate; matches the original else-branch
        (1, "A, B, C, or D"),   # degenerate; matches the original else-branch
        (2, "A or B"),
        (3, "A, B, or C"),
        (4, "A, B, C, or D"),
    ])
    def test_preserved_phrasing_for_realistic_range(self, n, expected):
        assert valid_letters_phrase(n) == expected

    @pytest.mark.parametrize("n,expected", [
        (5, "A, B, C, D, or E"),
        (6, "A, B, C, D, E, or F"),
    ])
    def test_generalizes_beyond_four(self, n, expected):
        # The latent bug: 5+ options used to also render as "A, B, C, or D".
        assert valid_letters_phrase(n) == expected


# ---------------------------------------------------------------------------
# build_mc_prompt
# ---------------------------------------------------------------------------

class TestBuildMcPrompt:
    def test_contains_question_and_lettered_options(self):
        p = build_mc_prompt("What is a fact table?", ["events", "lookups"])
        assert "What is a fact table?" in p
        assert "A. events" in p
        assert "B. lookups" in p

    def test_research_context_is_injected(self):
        p = build_mc_prompt("q", ["a", "b"], research_context="CDC triggers => TRUE")
        assert "<research_context>\nCDC triggers => TRUE\n</research_context>" in p

    def test_empty_research_context_keeps_empty_block(self):
        # The block is always present; an empty context leaves a blank line.
        p = build_mc_prompt("q", ["a", "b"])
        assert "<research_context>\n\n</research_context>" in p

    def test_single_select_wording(self):
        p = build_mc_prompt("q", ["a", "b", "c", "d"], multi_select=False)
        assert "This is a SINGLE-SELECT question. Choose the ONE best answer." in p
        assert "[Single letter only: A, B, C, or D]" in p

    def test_multi_select_wording(self):
        p = build_mc_prompt("q", ["a", "b", "c", "d"], multi_select=True)
        assert "This is a MULTI-SELECT question." in p
        assert "[One or more letters, comma-separated if multiple: A, B, C, or D]" in p

    def test_two_option_phrasing_preserved(self):
        # Pins the byte-for-byte-preserved two-option phrasing.
        p = build_mc_prompt("q", ["yes", "no"])
        assert "[Single letter only: A or B]" in p

    def test_five_options_are_all_offered(self):
        # Regression guard for the >4 cap: the fifth letter must appear.
        p = build_mc_prompt("q", ["a", "b", "c", "d", "e"])
        assert "E. e" in p
        assert "[Single letter only: A, B, C, D, or E]" in p

    def test_has_structural_sections(self):
        p = build_mc_prompt("q", ["a", "b"])
        assert "<question>" in p and "<options>" in p
        assert "<thinking>" in p and "<answer>" in p
        # All seven numbered instructions survive.
        for n in range(1, 8):
            assert f"\n{n}. " in p


# ---------------------------------------------------------------------------
# build_text_prompt
# ---------------------------------------------------------------------------

class TestBuildTextPrompt:
    def test_includes_question_and_requirements(self):
        p = build_text_prompt("Design a star schema for sales.")
        assert "**Question:** Design a star schema for sales." in p
        assert "REQUIREMENTS:" in p
        assert p.rstrip().endswith("Your response:")

    def test_no_feedback_section_by_default(self):
        p = build_text_prompt("q")
        assert "Previous attempt feedback" not in p

    def test_feedback_section_when_provided(self):
        p = build_text_prompt("q", feedback="Add more detail on grain.")
        assert "**Previous attempt feedback:**" in p
        assert "Add more detail on grain." in p
        assert "Please improve your answer based on this feedback." in p

    def test_empty_feedback_is_treated_as_none(self):
        # Falsy feedback must not emit an empty feedback block.
        assert "Previous attempt feedback" not in build_text_prompt("q", feedback="")


# ---------------------------------------------------------------------------
# normalize_sql_columns
# ---------------------------------------------------------------------------

class TestNormalizeSqlColumns:
    def test_dict_columns_split_into_specs_and_names(self):
        cols = [{"name": "sale_id", "type": "integer"}, {"name": "amount", "type": "double"}]
        specs, names = normalize_sql_columns(cols)
        assert specs == ["sale_id (integer)", "amount (double)"]
        assert names == ["sale_id", "amount"]

    def test_string_columns_pass_through_both(self):
        specs, names = normalize_sql_columns(["a", "b"])
        assert specs == ["a", "b"]
        assert names == ["a", "b"]

    def test_empty_is_two_empty_lists(self):
        assert normalize_sql_columns([]) == ([], [])


# ---------------------------------------------------------------------------
# build_sql_prompt
# ---------------------------------------------------------------------------

class TestBuildSqlPrompt:
    def test_core_sections(self):
        p = build_sql_prompt(
            "Running total per salesperson.",
            "bootcamp.sales",
            [{"name": "salesperson", "type": "varchar"}, {"name": "running_total", "type": "double"}],
        )
        assert "**Question:** Running total per salesperson." in p
        assert "**Available Table:** bootcamp.sales" in p
        # Columns are numbered with their types.
        assert "  1. salesperson (varchar)" in p
        assert "  2. running_total (double)" in p
        # Exact-order requirement uses bare names.
        assert "1. SELECT columns in EXACT order: salesperson, running_total" in p
        # Trino guidance is present.
        assert "Trino/Presto SQL syntax" in p
        assert p.rstrip().endswith("SQL:")

    def test_string_columns_supported(self):
        p = build_sql_prompt("q", "t", ["a", "b"])
        assert "  1. a" in p and "  2. b" in p
        assert "1. SELECT columns in EXACT order: a, b" in p

    def test_sample_data_section_optional(self):
        without = build_sql_prompt("q", "t", ["a"])
        assert "Sample Data from Table" not in without
        with_sd = build_sql_prompt("q", "t", ["a"], sample_data="COLUMNS: a\nRow 1: 1")
        assert "**Sample Data from Table (SELECT * LIMIT 3):**" in with_sd
        assert "COLUMNS: a\nRow 1: 1" in with_sd

    def test_feedback_section_optional(self):
        without = build_sql_prompt("q", "t", ["a"])
        assert "Previous attempt feedback" not in without
        with_fb = build_sql_prompt("q", "t", ["a"], feedback="VALIDATION ERROR: wrong rows")
        assert "**Previous attempt feedback:**" in with_fb
        assert "VALIDATION ERROR: wrong rows" in with_fb
        assert "Please fix the SQL based on this feedback." in with_fb

    def test_empty_columns_render_empty_order_line(self):
        # Degenerate input must not crash; the order line just has no names. The
        # trailing space after the colon is intentional (``', '.join([]) == ""``)
        # and is pinned so a future strip()/refactor can't silently drop it.
        p = build_sql_prompt("q", "t", [])
        assert "1. SELECT columns in EXACT order: \n" in p


# ---------------------------------------------------------------------------
# Golden full-prompt equality
# ---------------------------------------------------------------------------
#
# The substring checks above pin individual behaviors, but they would not catch a
# stray blank line slipping in *between* sections. These two whole-prompt equality
# checks make the byte-for-byte guarantee (verified against the original inline
# f-strings over 90k randomized inputs at extraction time) a permanent regression
# guard for one canonical MC prompt and one canonical SQL prompt.

EXPECTED_MC = """You are answering a multiple choice question from a data engineering bootcamp quiz.

<research_context>

</research_context>

<question>
What is a fact table?
</question>

<options>
A. events
B. lookups
</options>

IMPORTANT: This is a SINGLE-SELECT question. Choose the ONE best answer.

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
[Single letter only: A or B]
</answer>"""

EXPECTED_SQL = """You are solving a SQL quiz question. The database uses Trino/Presto SQL syntax.

**Question:** List all sales.

**Available Table:** bootcamp.sales

**Expected Output Columns (in exact order with data types):**
  1. sale_id (integer)
  2. amount (double)

CRITICAL REQUIREMENTS:
1. SELECT columns in EXACT order: sale_id, amount
2. Column names must match EXACTLY (use AS to rename if needed)
3. Use Trino/Presto SQL syntax (NOT PostgreSQL)
4. Do NOT use DISTINCT ON (use ROW_NUMBER() OVER instead)
5. Do NOT use INTERVAL syntax like '30 minutes' - use date_diff() or date_add() functions
6. Return ONLY the SQL query - no explanations, no markdown

TRINO JSON FUNCTIONS (use these, not PostgreSQL syntax):
- json_extract_scalar(column, '$.field') - returns VARCHAR
- json_extract(column, '$.array') - returns JSON
- CAST(json_extract(col, '$.items') AS ARRAY(ROW(sku VARCHAR, price DOUBLE, qty INTEGER))) - for arrays
- Use CROSS JOIN UNNEST(...) AS t(field1, field2) to flatten arrays

HOW TO INTERPRET VALIDATION ERRORS:
- 'Right answer has N rows. Your query has M rows' → Use WHERE to filter, NOT LIMIT or ORDER BY
  Example: 'Only include items where total_price > 25' means WHERE total_price > 25
- 'Value should be X but value is Y' → Check your WHERE/filter conditions
- 'column: region ! Value should be US but value is null' → The field is in a nested location
  Check the sample data to find where region/channel are located (maybe inside items array)

SQL:"""


class TestGoldenPrompts:
    def test_mc_prompt_exact(self):
        got = build_mc_prompt("What is a fact table?", ["events", "lookups"])
        assert got == EXPECTED_MC

    def test_sql_prompt_exact(self):
        got = build_sql_prompt(
            "List all sales.",
            "bootcamp.sales",
            [{"name": "sale_id", "type": "integer"}, {"name": "amount", "type": "double"}],
        )
        assert got == EXPECTED_SQL
