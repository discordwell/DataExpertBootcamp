"""Tests for the pure page-text interpreters in ``quiz_status``.

The score regex and the perfect/completed/not-started decisions used to be
inlined and duplicated three times inside ``run_quizzes_v2``'s browser coroutines
(once per call site of the ``X/Y (Z%)`` score regex), where they could not be
tested. Extracting them makes the fiddly cases — most importantly *not* mistaking
a calendar date like ``26/12/2025`` for a score — unit-testable with no browser.
"""
import pytest

from quiz_status import (
    PASS_THRESHOLD_PCT,
    AnswerResult,
    MCQuestion,
    QuestionProgress,
    QuizSummary,
    ResultTally,
    Score,
    classify_status,
    interpret_answer_result,
    interpret_text_result,
    is_perfect_completion,
    is_quiz_complete,
    parse_mc_question,
    parse_question_progress,
    parse_score,
    question_advanced,
    summarize_quiz,
    tally_quiz_results,
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


# ---------------------------------------------------------------------------
# interpret_text_result  (the free-form text-response counterpart)
# ---------------------------------------------------------------------------

class TestInterpretTextResult:
    # --- Positive verdicts the text grader can emit. These must read as a pass,
    # matching the old inline check's positive vocabulary.

    @pytest.mark.parametrize("text", [
        "Correct",
        "Well done!",
        "Your response passed.",
        "Answer accepted — great work.",
        "success",
        "Good answer.",  # a bare "good" alone is still a pass (unchanged behavior)
    ])
    def test_positive_words_read_as_correct(self, text):
        r = interpret_text_result(text)
        assert (r.correct, r.incorrect) == (True, False)

    # --- The bug this function fixes: a loose positive word sitting next to an
    # explicit negative used to bank the answer as correct. The negative now wins.

    def test_good_next_to_incorrect_is_a_miss(self):
        r = interpret_text_result("A good attempt, but incorrect.")
        assert (r.correct, r.incorrect) == (False, True)

    def test_good_next_to_try_again_is_a_miss(self):
        r = interpret_text_result("Good start, but try again with more detail.")
        assert (r.correct, r.incorrect) == (False, True)

    # --- Plain negatives.

    @pytest.mark.parametrize("text", [
        "Incorrect",
        "Incorrect. The correct answer needs the partition clause.",  # lowercase "correct" is not a pass
        "Please try again.",
    ])
    def test_negative_words_read_as_incorrect(self, text):
        r = interpret_text_result(text)
        assert (r.correct, r.incorrect) == (False, True)

    # --- Neither verdict yet (still mid-submission / unrecognized).

    def test_unclear_is_neither(self):
        r = interpret_text_result("Submitting your response...")
        assert r == AnswerResult(correct=False, incorrect=False, complete=False)

    # --- complete mirrors is_quiz_complete's default markers, like the MC/SQL one.

    def test_complete_marker(self):
        assert interpret_text_result("Quiz Complete").complete is True

    def test_pass_and_complete_together(self):
        r = interpret_text_result("Well done! Quiz Complete")
        assert r == AnswerResult(correct=True, incorrect=False, complete=True)


# ---------------------------------------------------------------------------
# parse_question_progress
# ---------------------------------------------------------------------------

class TestParseQuestionProgress:
    def test_basic(self):
        assert parse_question_progress("Question 1 of 6") == QuestionProgress(1, 6)

    def test_multi_digit(self):
        assert parse_question_progress("Question 12 of 30") == QuestionProgress(12, 30)

    def test_embedded_in_surrounding_text(self):
        text = "25% Complete\nQuestion 3 of 4\nSingle Choice\nWhat is ...?"
        assert parse_question_progress(text) == QuestionProgress(3, 4)

    def test_returns_first_match(self):
        # The live page shows one marker, but pin first-match behavior regardless.
        assert parse_question_progress("Question 2 of 5 ... Question 9 of 9") == QuestionProgress(2, 5)

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "Start Quiz to begin",
            "Quiz Complete! You passed",
            "Question of",            # no numbers
            "Question 3 of",          # missing total
            "question 3 of 6",        # lowercase 'q' does not match
        ],
    )
    def test_no_marker_returns_none(self, text):
        assert parse_question_progress(text) is None

    def test_fields_are_ints(self):
        progress = parse_question_progress("Question 4 of 8")
        assert (progress.current, progress.total) == (4, 8)
        assert isinstance(progress.current, int) and isinstance(progress.total, int)

    def test_matches_legacy_inline_regex(self):
        # Differential check: the helper must agree with the exact regex the four
        # runner call sites used inline before extraction.
        import re

        legacy = re.compile(r'Question (\d+) of (\d+)')
        samples = [
            "",
            "Question 1 of 6",
            "Question 12 of 30",
            "25% Complete\nQuestion 3 of 4\nSingle Choice",
            "Question 3 of",
            "no marker here",
            "Question 2 of 5 ... Question 9 of 9",
            "Quiz Complete",
            "QUESTION 1 OF 2",
        ]
        for text in samples:
            m = legacy.search(text)
            expected = QuestionProgress(int(m.group(1)), int(m.group(2))) if m else None
            assert parse_question_progress(text) == expected, text


# ---------------------------------------------------------------------------
# question_advanced
# ---------------------------------------------------------------------------

class TestQuestionAdvanced:
    def test_next_question_is_an_advance(self):
        assert question_advanced(QuestionProgress(2, 6), QuestionProgress(3, 6)) is True

    def test_same_question_is_not_an_advance(self):
        assert question_advanced(QuestionProgress(2, 6), QuestionProgress(2, 6)) is False

    def test_earlier_question_is_not_an_advance(self):
        # Defensive: a re-render showing an earlier position must not break the wait.
        assert question_advanced(QuestionProgress(4, 6), QuestionProgress(1, 6)) is False

    def test_none_is_not_an_advance(self):
        # No "Question N of M" on screen (mid-transition or results page): the
        # wait loop's separate completion check handles the results page; a bare
        # None must not read as "advanced".
        assert question_advanced(QuestionProgress(2, 6), None) is False

    def test_skipping_ahead_counts_as_advanced(self):
        assert question_advanced(QuestionProgress(2, 6), QuestionProgress(5, 6)) is True

    def test_fixes_the_loop_counter_off_by_one(self):
        # The scenario the old `current > q_num + 1` check got wrong: question 2
        # was answered on loop iteration 2 (an earlier iteration was consumed by
        # a stuck-wait), so the old check demanded current > 3 and kept spinning
        # after question 3 had already loaded.
        answered = QuestionProgress(2, 6)   # just answered Q2...
        q_num = 2                           # ...on 0-based loop iteration 2
        seen = QuestionProgress(3, 6)       # Q3 is now on screen
        assert (seen.current > q_num + 1) is False  # old check: still waiting
        assert question_advanced(answered, seen) is True  # new check: advanced


# ---------------------------------------------------------------------------
# parse_mc_question
# ---------------------------------------------------------------------------

# The realistic modal layout: the choice-type badge sits between "% Complete"
# and the question, and the option lines run up to "Show Hint".
REAL_MODAL = """\
Data Modeling Quiz
Question 2 of 6
17% Complete
Single Choice
What is a slowly changing dimension?
A dimension that changes over time and requires versioning
A dimension that never changes
A table with no primary key
A fact table containing only measures
Show Hint
Check Answer"""


class TestParseMCQuestion:
    def test_realistic_modal(self):
        parsed = parse_mc_question(REAL_MODAL)
        assert parsed == MCQuestion(
            "What is a slowly changing dimension?",
            [
                "A dimension that changes over time and requires versioning",
                "A dimension that never changes",
                "A table with no primary key",
                "A fact table containing only measures",
            ],
        )

    def test_badge_line_is_not_the_question(self):
        # The bug the old quiz_solver inline parse had: the line right after
        # "% Complete" is the "Single Choice" badge, and it took that as the
        # question. The badge must be skipped.
        assert parse_mc_question(REAL_MODAL).question != "Single Choice"

    def test_question_line_is_not_an_option(self):
        # ...and because the question follows the badge, the old parse also
        # swept the question into the options list. It must be excluded.
        parsed = parse_mc_question(REAL_MODAL)
        assert parsed.question not in parsed.options

    def test_question_before_badge_layout(self):
        # Alternate layout: question between "% Complete" and the badge.
        text = (
            "Question 1 of 5\n20% Complete\n"
            "Which property describes an idempotent pipeline?\n"
            "Multiple Choice\n"
            "Same result no matter how many times it runs\n"
            "Runs exactly once\n"
            "Check Answer"
        )
        parsed = parse_mc_question(text)
        assert parsed.question == "Which property describes an idempotent pipeline?"
        assert parsed.options == [
            "Same result no matter how many times it runs",
            "Runs exactly once",
        ]

    def test_options_stop_at_show_hint(self):
        parsed = parse_mc_question(REAL_MODAL)
        assert "Show Hint" not in parsed.options
        assert "Check Answer" not in parsed.options

    def test_options_stop_at_check_answer_when_no_hint(self):
        text = (
            "50% Complete\nSingle Choice\nWhat does ACID stand for in databases?\n"
            "Atomicity, Consistency, Isolation, Durability\n"
            "Availability, Consistency, Integrity, Distribution\n"
            "Check Answer\nNot an option"
        )
        parsed = parse_mc_question(text)
        assert parsed.options == [
            "Atomicity, Consistency, Isolation, Durability",
            "Availability, Consistency, Integrity, Distribution",
        ]

    def test_navigation_labels_are_not_options(self):
        text = (
            "10% Complete\nSingle Choice\nWhat is a fact table used for?\n"
            "Notes\nStoring measures\nQuiz\nStoring dimensions\nPrevious\nNext\nModule\n"
            "Show Hint"
        )
        parsed = parse_mc_question(text)
        assert parsed.options == ["Storing measures", "Storing dimensions"]

    def test_option_cap(self):
        options = "\n".join(f"Option number {i}" for i in range(1, 9))
        text = f"10% Complete\nSingle Choice\nWhich options apply to this question?\n{options}\nShow Hint"
        parsed = parse_mc_question(text)
        assert len(parsed.options) == 6
        assert parsed.options[0] == "Option number 1"

    def test_question_window_skips_short_lines(self):
        # The question is the first line longer than 10 chars after the badge —
        # short interstitial lines are skipped (same rule as the primary
        # runner's DOM parser).
        text = (
            "33% Complete\nSingle Choice\n1 of 3\n"
            "Which join returns every row from both tables?\n"
            "FULL OUTER JOIN\nINNER JOIN\nShow Hint"
        )
        parsed = parse_mc_question(text)
        assert parsed.question == "Which join returns every row from both tables?"

    def test_no_percent_complete_marker_returns_none(self):
        assert parse_mc_question("Single Choice\nA question?\nopt\nShow Hint") is None

    def test_no_badge_means_no_options_returns_none(self):
        assert parse_mc_question("50% Complete\nWhat is a data warehouse used for?") is None

    def test_empty_text_returns_none(self):
        assert parse_mc_question("") is None

    def test_question_too_far_from_progress_marker_returns_none(self):
        # The question must appear within the 4 lines after "% Complete";
        # anything later is out of the window (mirrors the primary runner).
        text = (
            "50% Complete\nfiller a\nfiller b\nfiller c\nfiller d\n"
            "The real question is way down here?\nSingle Choice\nan option line here\nShow Hint"
        )
        assert parse_mc_question(text) is None


# ---------------------------------------------------------------------------
# summarize_quiz
# ---------------------------------------------------------------------------

class TestSummarizeQuiz:
    def test_threshold_is_seventy_percent(self):
        # Documents the shared pass rule both runners key off.
        assert PASS_THRESHOLD_PCT == 70

    def test_clear_pass(self):
        s = summarize_quiz(8, 10)
        assert s == QuizSummary(80.0, "PASSED", True)

    def test_clear_fail_uses_rounded_percent_label(self):
        s = summarize_quiz(6, 10)
        assert s == QuizSummary(60.0, "60%", False)

    def test_perfect(self):
        s = summarize_quiz(5, 5)
        assert s.passed is True
        assert s.status == "PASSED"
        assert s.pct == 100.0

    def test_zero_correct(self):
        s = summarize_quiz(0, 5)
        assert s == QuizSummary(0.0, "0%", False)

    def test_exact_threshold_passes(self):
        # 7/10 sits exactly on the 70% line and must count as a pass (the gate is
        # `>= 70`, inclusive), matching the runners' inline check.
        assert summarize_quiz(7, 10).passed is True

    def test_label_rounds_like_the_runner(self):
        # The label uses `f"{pct:.0f}%"`, so 2/3 = 66.66% rounds to "67%".
        assert summarize_quiz(2, 3).status == "67%"
        assert summarize_quiz(1, 3).status == "33%"

    def test_empty_quiz_is_safe(self):
        # The runners guard with `if total > 0`, but the helper must not divide by
        # zero if handed an empty tally.
        assert summarize_quiz(0, 0) == QuizSummary(0.0, "0%", False)

    def test_all_correct_scores_full_marks(self):
        # Regression context for the text-answer scoring fix: once every correct
        # answer (including free-form text) is counted in `score`, a fully-correct
        # quiz summarizes as 100% PASSED — before the fix a correct text answer
        # was left out of `score` but still counted in the denominator, dragging
        # the percentage (and the pass gate) below the true value.
        assert summarize_quiz(4, 4) == QuizSummary(100.0, "PASSED", True)

    def test_matches_the_inline_logic_it_replaces(self):
        # Differential check against the exact expression both runners computed
        # inline before extraction:
        #     pct = (score / total) * 100
        #     status = "PASSED" if pct >= 70 else f"{pct:.0f}%"
        #     passed = pct >= 70
        # This pins the boundary behavior (including any float rounding) to the
        # original, so the extraction cannot silently change a pass/fail verdict.
        cases = [
            (0, 1), (1, 1), (1, 3), (2, 3), (3, 4), (5, 7),
            (6, 10), (7, 10), (8, 10), (13, 20), (14, 20),
            (69, 100), (70, 100), (71, 100), (1, 8), (49, 50),
        ]
        for score, total in cases:
            pct = (score / total) * 100
            expected = QuizSummary(pct, "PASSED" if pct >= 70 else f"{pct:.0f}%", pct >= 70)
            assert summarize_quiz(score, total) == expected, (score, total)


def _quiz(completed, questions, score):
    """A per-quiz result dict shaped like the runners build."""
    return {"completed": completed, "questions": [None] * questions, "score": score}


class TestTallyQuizResults:
    def test_empty_run(self):
        # No quizzes: everything zero, and the percentage is a divide-by-zero-safe
        # 0.0 (not a crash).
        assert tally_quiz_results([]) == ResultTally(0, 0, 0, 0.0)

    def test_single_perfect_quiz(self):
        assert tally_quiz_results([_quiz(True, 5, 5)]) == ResultTally(1, 5, 5, 100.0)

    def test_sums_across_quizzes(self):
        # Two passed, one failed; totals accumulate and the percentage is over the
        # grand totals (11/16), not an average of per-quiz percentages.
        results = [_quiz(True, 5, 5), _quiz(True, 6, 5), _quiz(False, 5, 1)]
        tally = tally_quiz_results(results)
        assert tally == ResultTally(2, 16, 11, 11 / 16 * 100)

    def test_error_placeholder_contributes_zero(self):
        # The v2 runner appends a bare {"slug", "title", "error"} dict when a quiz
        # raises. Missing completed/questions/score keys must count as zero, not
        # raise KeyError — this is the .get() robustness the helper guarantees for
        # both runners.
        results = [_quiz(True, 4, 4), {"slug": "x", "title": "X", "error": "boom"}]
        assert tally_quiz_results(results) == ResultTally(1, 4, 4, 100.0)

    def test_completed_but_zero_questions(self):
        # A quiz skipped as already-perfect is recorded completed with an empty
        # questions list and score 1 (see solve_quiz's early return). It counts as
        # passed but contributes no answered questions.
        assert tally_quiz_results([{"completed": True, "questions": [], "score": 1}]) == ResultTally(
            1, 0, 1, 0.0
        )

    def test_passed_counts_truthy_completed_only(self):
        # `passed` counts quizzes whose `completed` is truthy; a missing or falsy
        # flag does not count.
        results = [_quiz(True, 1, 1), _quiz(False, 1, 0), {"questions": [None], "score": 0}]
        assert tally_quiz_results(results).passed == 1

    def test_matches_the_inline_logic_it_replaces(self):
        # Differential check against the exact expressions the two runners computed
        # inline before extraction (v2's summary used .get() defaults; run_all's
        # used direct keys over its always-complete dicts). Over full result dicts
        # the two agree, so pin the helper to that shared behavior.
        runs = [
            [],
            [_quiz(True, 5, 5)],
            [_quiz(True, 5, 5), _quiz(False, 6, 3)],
            [_quiz(True, 7, 7), _quiz(True, 3, 3), _quiz(False, 10, 6)],
            [_quiz(False, 8, 0), _quiz(True, 1, 1)],
        ]
        for results in runs:
            passed = sum(1 for r in results if r.get("completed", False))
            total_q = sum(len(r.get("questions", [])) for r in results)
            total_c = sum(r.get("score", 0) for r in results)
            pct = (total_c / total_q * 100) if total_q > 0 else 0
            tally = tally_quiz_results(results)
            assert (tally.passed, tally.total_questions, tally.total_correct) == (
                passed,
                total_q,
                total_c,
            ), results
            # The old inline pct was int 0 for the empty case; the helper returns
            # float 0.0, but both render identically under the runners' f"{pct:.0f}%".
            assert f"{tally.pct:.0f}" == f"{pct:.0f}", results
