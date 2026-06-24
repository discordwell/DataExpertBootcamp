"""Tests for the pure page-text interpreters in ``quiz_status``.

The score regex and the perfect/completed/not-started decisions used to be
inlined and duplicated three times inside ``run_quizzes_v2``'s browser coroutines
(once per call site of the ``X/Y (Z%)`` score regex), where they could not be
tested. Extracting them makes the fiddly cases — most importantly *not* mistaking
a calendar date like ``26/12/2025`` for a score — unit-testable with no browser.
"""
import pytest

from quiz_status import (
    AnswerResult,
    Score,
    classify_status,
    interpret_answer_result,
    is_perfect_completion,
    is_quiz_complete,
    parse_score,
)


# ---------------------------------------------------------------------------
# parse_score
# ---------------------------------------------------------------------------

class TestParseScore:
    def test_basic_score(self):
        assert parse_score("You scored 5/5 (100%)") == Score(5, 5, 100)

    def test_partial_score(self):
        assert parse_score("Score: 3/5 (60%)") == Score(3, 5, 60)

    def test_zero_score(self):
        assert parse_score("0/7 (0%)") == Score(0, 7, 0)

    def test_tolerates_whitespace_before_percent(self):
        assert parse_score("4/8   (50%)") == Score(4, 8, 50)

    def test_no_score_returns_none(self):
        assert parse_score("Start Quiz to begin") is None
        assert parse_score("") is None

    def test_date_is_not_mistaken_for_a_score(self):
        # The whole point of requiring a trailing "(N%)": a bare date must not
        # parse as got/total. This was the documented regression motivating the
        # regex shape.
        assert parse_score("Completed on 26/12/2025") is None
        assert parse_score("Due 01/02/2024, not started") is None

    def test_bare_percentage_is_not_a_full_score(self):
        # "(100%)" with no fraction is not a parseable Score (parse_score is the
        # strict X/Y (Z%) form); the bare marker is handled elsewhere.
        assert parse_score("Lesson Completed (100%)") is None

    def test_returns_first_score_when_several(self):
        assert parse_score("old 2/5 (40%) ... now 5/5 (100%)") == Score(2, 5, 40)


# ---------------------------------------------------------------------------
# Score.is_perfect / __str__
# ---------------------------------------------------------------------------

class TestScore:
    def test_perfect_requires_full_and_hundred_percent(self):
        assert Score(5, 5, 100).is_perfect is True

    def test_not_perfect_when_below_hundred(self):
        assert Score(4, 5, 80).is_perfect is False

    def test_not_perfect_when_hundred_pct_but_not_all_correct(self):
        # Contradictory but defensive: 100% must also mean got == total.
        assert Score(4, 5, 100).is_perfect is False

    def test_str_format(self):
        assert str(Score(5, 5, 100)) == "5/5 (100%)"
        assert str(Score(3, 7, 42)) == "3/7 (42%)"


# ---------------------------------------------------------------------------
# is_perfect_completion
# ---------------------------------------------------------------------------

class TestIsPerfectCompletion:
    def test_perfect_score_is_perfect(self):
        assert is_perfect_completion("passed the quiz 5/5 (100%)") is True

    def test_partial_score_is_not_perfect(self):
        assert is_perfect_completion("3/5 (60%) keep going") is False

    def test_bare_hundred_percent_without_fraction_is_perfect(self):
        # Fallback path: no X/Y fraction, but a bare "(100%)" marker is present.
        assert is_perfect_completion("Lesson Completed (100%)") is True

    def test_bare_other_percentage_is_not_perfect(self):
        assert is_perfect_completion("Lesson Completed (80%)") is False

    def test_no_markers_is_not_perfect(self):
        assert is_perfect_completion("Start Quiz") is False

    def test_real_score_beats_a_stray_hundred_marker(self):
        # A genuine 3/5 (60%) is not perfect even if "(100%)" appears elsewhere
        # on the page (e.g. an unrelated progress widget): the fraction wins.
        assert is_perfect_completion("3/5 (60%) ... bonus (100%)") is False


# ---------------------------------------------------------------------------
# classify_status
# ---------------------------------------------------------------------------

class TestClassifyStatus:
    def test_perfect(self):
        assert classify_status("5/5 (100%)") == ("perfect", "5/5 (100%)")

    def test_incomplete(self):
        assert classify_status("2/5 (40%)") == ("incomplete", "2/5 (40%)")

    def test_completed_with_bare_percentage(self):
        assert classify_status("Lesson Completed (90%)") == ("completed", "(90%)")

    def test_completed_without_percentage(self):
        status, score = classify_status("You passed the quiz earlier")
        assert status == "completed"
        assert score is None

    def test_not_started(self):
        assert classify_status("Start Quiz") == ("not_started", None)

    def test_unknown(self):
        assert classify_status("some unrelated lesson text") == ("unknown", None)

    def test_score_fraction_takes_precedence_over_completed_marker(self):
        # An explicit fraction classifies directly, even alongside a "Lesson
        # Completed" marker.
        assert classify_status("Lesson Completed 4/4 (100%)") == ("perfect", "4/4 (100%)")

    def test_date_does_not_classify_as_a_score(self):
        # A "Lesson Completed" page dated 26/12/2025 is "completed", not a score.
        assert classify_status("Lesson Completed on 26/12/2025") == ("completed", None)


# ---------------------------------------------------------------------------
# is_quiz_complete
# ---------------------------------------------------------------------------

class TestIsQuizComplete:
    @pytest.mark.parametrize("text", ["Quiz Complete", "You passed!", "...You passed..."])
    def test_default_markers(self, text):
        assert is_quiz_complete(text) is True

    def test_progress_marker_needs_opt_in(self):
        # "100% Complete" only counts when check_progress=True.
        assert is_quiz_complete("100% Complete") is False
        assert is_quiz_complete("100% Complete", check_progress=True) is True

    def test_default_markers_still_fire_with_progress_flag(self):
        assert is_quiz_complete("Quiz Complete", check_progress=True) is True

    def test_not_complete(self):
        assert is_quiz_complete("Question 3 of 6") is False
        assert is_quiz_complete("Question 3 of 6", check_progress=True) is False


# ---------------------------------------------------------------------------
# interpret_answer_result
# ---------------------------------------------------------------------------

class TestInterpretAnswerResult:
    # --- The strings the live grader actually emits. On these, the consolidated
    # interpreter must agree with every runner's old inline check (no regression).

    def test_mc_or_text_pass(self):
        assert interpret_answer_result("Correct! Well done.") == AnswerResult(
            correct=True, incorrect=False, complete=False
        )

    def test_sql_pass_with_banged_correct(self):
        r = interpret_answer_result("Correct! Output matches expected output.")
        assert (r.correct, r.incorrect) == (True, False)

    def test_sql_pass_without_bang(self):
        # SQL grader can report success via "Output matches" with no "Correct!".
        r = interpret_answer_result("Output matches expected output")
        assert (r.correct, r.incorrect) == (True, False)

    def test_mc_miss(self):
        # Note the explanatory lowercase "correct" must NOT read as a pass.
        r = interpret_answer_result("Incorrect. The correct answer is B.")
        assert (r.correct, r.incorrect) == (False, True)

    def test_sql_miss(self):
        r = interpret_answer_result("Incorrect. Your output does not match the expected output.")
        assert (r.correct, r.incorrect) == (False, True)

    def test_mid_quiz_no_verdict_yet(self):
        r = interpret_answer_result("Question 3 of 6")
        assert r == AnswerResult(correct=False, incorrect=False, complete=False)

    # --- Edge cases that motivated centralizing this (the old inline copies had
    # drifted on exactly these).

    def test_output_matches_guarded_by_does_not_match(self):
        # "does not match" anywhere vetoes a stray "Output matches" — the v2 SQL
        # site lacked this guard before; now it matches the v2 MC site.
        r = interpret_answer_result("Output matches header, but result does not match")
        assert (r.correct, r.incorrect) == (False, True)

    def test_bare_unbanged_correct_is_not_a_pass(self):
        # The proven primary runner keys off "Correct!"; a bare "Correct" (as in
        # "The Correct answer was...") is not a success signal. The older runners
        # used to fire on it.
        assert interpret_answer_result("The Correct option is highlighted.").correct is False

    def test_incorrect_substring_correct_is_not_a_pass(self):
        # "Incorrect" contains a lowercase "correct" but not "Correct!".
        assert interpret_answer_result("Incorrect").correct is False

    # --- complete mirrors is_quiz_complete's default markers.

    @pytest.mark.parametrize("text", ["Quiz Complete", "You passed!"])
    def test_complete_markers(self, text):
        assert interpret_answer_result(text).complete is True

    def test_progress_bar_is_not_complete_here(self):
        # interpret_answer_result uses the *default* (non-progress) markers, so a
        # bare "100% Complete" progress bar is not yet "complete".
        assert interpret_answer_result("100% Complete").complete is False

    def test_pass_and_complete_together(self):
        r = interpret_answer_result("Correct! Quiz Complete")
        assert r == AnswerResult(correct=True, incorrect=False, complete=True)
