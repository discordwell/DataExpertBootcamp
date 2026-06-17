"""Tests for the pure Claude-response parsers in ``quiz_parsing``.

These functions used to live inside the subprocess-calling solver functions in
``run_quizzes_v2.py``; extracting them makes the fiddly LLM-output parsing (letter
extraction, multi-select de-duplication, markdown SQL fences, preamble stripping)
unit-testable with no browser or CLI.
"""
import pytest

from quiz_parsing import clean_text_response, extract_sql, parse_mc_answer


# ---------------------------------------------------------------------------
# parse_mc_answer
# ---------------------------------------------------------------------------

class TestParseMcAnswer:
    def test_answer_block_single_letter(self):
        assert parse_mc_answer("<answer>A</answer>", 4) == [0]
        assert parse_mc_answer("<answer>C</answer>", 4) == [2]
        assert parse_mc_answer("<answer>D</answer>", 4) == [3]

    def test_answer_block_is_case_insensitive(self):
        assert parse_mc_answer("<answer>b</answer>", 4) == [1]

    def test_answer_block_with_surrounding_whitespace(self):
        assert parse_mc_answer("<answer>  C  </answer>", 4) == [2]

    def test_thinking_then_answer_block_uses_the_block(self):
        # Stray letters appear in the reasoning, but the <answer> block wins.
        resp = "<thinking>Could be A or B...</thinking>\n<answer>D</answer>"
        assert parse_mc_answer(resp, 4) == [3]

    def test_single_select_takes_first_index_in_answer_block(self):
        # Two letters in a single-select answer -> only the first is used.
        assert parse_mc_answer("<answer>B, C</answer>", 4, multi_select=False) == [1]

    def test_multi_select_returns_all_letters_in_block(self):
        assert parse_mc_answer("<answer>A, C</answer>", 4, multi_select=True) == [0, 2]

    def test_fallback_single_select_takes_last_letter(self):
        # No <answer> block: trust the last standalone letter (the conclusion).
        assert parse_mc_answer("Between A and D, I pick D", 4) == [3]

    def test_fallback_finds_standalone_letter(self):
        assert parse_mc_answer("I'll go with C here.", 4) == [2]

    def test_fallback_ignores_letters_inside_words(self):
        # "AND" / "DATA" must not be read as options A or D.
        assert parse_mc_answer("AND the DATA shows option B", 4) == [1]

    def test_fallback_multi_select_dedupes_preserving_order(self):
        assert parse_mc_answer("A and B and A again", 4, multi_select=True) == [0, 1]

    def test_letter_out_of_range_is_ignored(self):
        # Only A/B are valid for a 2-option question; D is dropped, no match -> [0].
        assert parse_mc_answer("<answer>D</answer>", 2) == [0]

    def test_no_usable_letter_falls_back_to_zero(self):
        assert parse_mc_answer("I really cannot tell.", 4) == [0]

    def test_zero_options_is_safe(self):
        # Robustness: the old inline code built an empty regex char class and
        # raised; the extracted function returns [0] instead.
        assert parse_mc_answer("<answer>A</answer>", 0) == [0]

    @pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
    def test_return_is_always_valid_nonempty(self, n):
        idx = parse_mc_answer("some response mentioning C and A", n)
        assert idx, "result must be non-empty"
        assert all(0 <= i < max(n, 1) for i in idx)


# ---------------------------------------------------------------------------
# extract_sql
# ---------------------------------------------------------------------------

class TestExtractSql:
    def test_fenced_sql_block(self):
        assert extract_sql("```sql\nSELECT * FROM t\n```") == "SELECT * FROM t"

    def test_bare_code_fence_with_select(self):
        assert extract_sql("```\nSELECT 1\n```") == "SELECT 1"

    def test_plain_select(self):
        assert extract_sql("SELECT a, b FROM t WHERE x > 1") == "SELECT a, b FROM t WHERE x > 1"

    def test_strips_leading_prose(self):
        assert extract_sql("Here is the query: SELECT a FROM t") == "SELECT a FROM t"

    def test_collapses_multiline_to_single_line(self):
        raw = "```sql\nWITH c AS (\n  SELECT 1\n)\nSELECT * FROM c\n```"
        assert extract_sql(raw) == "WITH c AS ( SELECT 1 ) SELECT * FROM c"

    def test_lowercase_keyword_preserved_but_accepted(self):
        assert extract_sql("select 1 from t") == "select 1 from t"

    @pytest.mark.parametrize("stmt", [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET x = 1",
        "DELETE FROM t WHERE x = 1",
    ])
    def test_other_statements_recognized(self, stmt):
        assert extract_sql(stmt) == stmt

    def test_no_sql_returns_none(self):
        assert extract_sql("I'm not sure how to answer this.") is None

    def test_empty_returns_none(self):
        assert extract_sql("") is None
        assert extract_sql("   \n  ") is None


# ---------------------------------------------------------------------------
# clean_text_response
# ---------------------------------------------------------------------------

class TestCleanTextResponse:
    def test_strips_here_is(self):
        assert clean_text_response("Here is my detailed answer") == "my detailed answer"

    def test_strips_my_answer_label(self):
        assert clean_text_response("My answer: use a fact table") == "use a fact table"

    def test_strips_response_label(self):
        assert clean_text_response("Response:  the design is...") == "the design is..."

    def test_case_insensitive(self):
        assert clean_text_response("HERE IS the plan") == "the plan"

    def test_leaves_clean_text_untouched(self):
        text = "A fact table stores measurable events."
        assert clean_text_response(text) == text

    def test_does_not_strip_similar_prefixes(self):
        # "Here islands" is not the "Here is " preamble (no following space match).
        assert clean_text_response("Here islands form slowly") == "Here islands form slowly"
