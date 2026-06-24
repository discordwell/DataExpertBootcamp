"""Pure helpers for interpreting a DataExpert quiz/lesson page's text.

The runners read ``document.body.innerText`` and then have to decide several
things from it: what score the page reports, whether a quiz is already perfect
(so it can be skipped on a re-run), how to classify the lesson for the status
report, and — after each "Check Answer" — whether the answer was graded
correct/incorrect and whether the quiz has finished.

That decision logic is pure regex/string work with genuine edge cases: the score
pattern must match a quiz score like ``5/5 (100%)`` but *not* a calendar date such
as ``26/12/2025``, and the correct/incorrect verdict must not be fooled by a
``"does not match"`` sitting next to an ``"Output matches"``. It used to be
inlined and duplicated across ``run_quizzes_v2``'s browser coroutines (the score
regex appeared at three call sites; the verdict check at two more) and across the
``run_all_quizzes`` / ``quiz_solver`` runners, where it could not be unit-tested
and had quietly drifted out of sync.

Like ``quiz_heuristics`` / ``quiz_sql`` / ``quiz_parsing``, this module is
browser-free, so it is covered directly by ``tests/test_quiz_status.py``.
"""
import re
from typing import NamedTuple, Optional, Tuple

# Matches a quiz score like "5/5 (100%)". The trailing "(N%)" is REQUIRED, which
# is what stops the pattern from matching a calendar date such as "26/12/2025"
# (a date has no percentage after it).
SCORE_RE = re.compile(r'(\d+)/(\d+)\s*\((\d+)%\)')

# Bare-percentage fallback, e.g. a "(100%)" with no "got/total" fraction.
PERCENT_RE = re.compile(r'\((\d+)%\)')


class Score(NamedTuple):
    """A parsed quiz score: ``got`` correct out of ``total``, at ``pct`` percent."""

    got: int
    total: int
    pct: int

    @property
    def is_perfect(self) -> bool:
        """A perfect score: 100% *and* every question correct."""
        return self.pct == 100 and self.got == self.total

    def __str__(self) -> str:
        return f"{self.got}/{self.total} ({self.pct}%)"


def parse_score(text: str) -> Optional[Score]:
    """Extract the first ``X/Y (Z%)`` quiz score from page text, or ``None``.

    Returns ``None`` when no score fraction is present (e.g. the page only shows a
    bare ``(100%)``, or shows a date like ``26/12/2025`` and nothing else).
    """
    m = SCORE_RE.search(text)
    if not m:
        return None
    return Score(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_perfect_completion(text: str) -> bool:
    """Whether the page shows an already-perfect quiz the runner should skip.

    Prefers the explicit ``X/Y (Z%)`` score (perfect == 100% *and* every question
    correct); when no fraction is present, falls back to a bare ``(100%)`` marker.
    This is the canonical "skip this quiz, it's done" rule the v2 runner applies
    before re-taking a quiz.
    """
    score = parse_score(text)
    if score is not None:
        return score.is_perfect
    return "(100%)" in text


def classify_status(text: str) -> Tuple[str, Optional[str]]:
    """Classify a quiz lesson page for the no-retake status report.

    Returns ``(status, score_str)`` where ``status`` is one of ``"perfect"``,
    ``"incomplete"``, ``"completed"``, ``"not_started"``, or ``"unknown"``, and
    ``score_str`` is a human-readable score when one could be determined (else
    ``None``).

    A page that reports an explicit ``X/Y (Z%)`` is ``perfect`` at 100% and
    ``incomplete`` otherwise. With no fraction, a "Lesson Completed"/"passed the
    quiz" page is ``completed`` (carrying any bare ``(Z%)`` it shows), a page still
    offering "Start Quiz" is ``not_started``, and anything else is ``unknown``.
    """
    score = parse_score(text)
    if score is not None:
        return ("perfect" if score.pct == 100 else "incomplete", str(score))
    if "Lesson Completed" in text or "passed the quiz" in text.lower():
        m = PERCENT_RE.search(text)
        return ("completed", f"({m.group(1)}%)" if m else None)
    if "Start Quiz" in text:
        return ("not_started", None)
    return ("unknown", None)


def is_quiz_complete(text: str, *, check_progress: bool = False) -> bool:
    """Whether page text indicates the in-progress quiz has finished.

    The runner detects completion in two situations with two marker sets. The
    default markers are ``"Quiz Complete"`` / ``"You passed"``; pass
    ``check_progress=True`` to also treat a ``"100% Complete"`` progress bar as
    done (used right after answering, where the progress bar is the live signal).
    """
    if "Quiz Complete" in text or "You passed" in text:
        return True
    if check_progress and "100% Complete" in text:
        return True
    return False


class AnswerResult(NamedTuple):
    """How the grader's feedback text reads after a single answer is checked.

    ``correct`` / ``incorrect`` are independent (a page may show neither yet);
    ``complete`` mirrors :func:`is_quiz_complete` with the default markers.
    """

    correct: bool
    incorrect: bool
    complete: bool


def interpret_answer_result(text: str) -> AnswerResult:
    """Interpret a post-"Check Answer" page's text into correct/incorrect/complete.

    This is the single source of truth for reading the grader's verdict, shared
    by every runner. It used to be re-inlined at four call sites that had quietly
    **drifted**: the v2 SQL site lacked the v2 MC site's ``"does not match"``
    guard, and the older ``run_all_quizzes`` / ``quiz_solver`` runners keyed off a
    looser bare ``"Correct"`` rather than the primary runner's proven ``"Correct!"``.

    The signals mirror the primary (49/49) runner:

    - ``correct``: an explicit ``"Correct!"``, or an ``"Output matches"`` SQL pass
      that is *not* contradicted by a ``"does not match"`` elsewhere on the page.
    - ``incorrect``: an explicit ``"Incorrect"`` or a SQL ``"does not match"``.
    - ``complete``: the quiz has finished (``is_quiz_complete``'s default markers).

    On the strings the live grader actually emits (``"Correct!"`` on a pass,
    ``"Incorrect"`` on a miss) this returns exactly what each runner's old inline
    check did; it only diverges on contrived inputs (a bare un-banged
    ``"Correct"``, or both ``"Output matches"`` and ``"does not match"`` at once).
    """
    correct = "Correct!" in text or ("Output matches" in text and "does not match" not in text)
    incorrect = "Incorrect" in text or "does not match" in text
    return AnswerResult(correct=correct, incorrect=incorrect, complete=is_quiz_complete(text))


def interpret_text_result(text: str) -> AnswerResult:
    """Interpret a post-"Check Answer" page for a *free-form text* answer.

    The free-form design/interview questions are graded with fuzzier language than
    the crisp multiple-choice / SQL grader that :func:`interpret_answer_result`
    reads, so this is its text-response counterpart. The positive vocabulary is
    wider ("Well done", "passed", "accepted", "great", a bare "good", ...) and,
    crucially, an explicit negative (``"Incorrect"`` / ``"try again"``) *vetoes*
    those looser positives — so feedback like "a good attempt, but incorrect" reads
    as a miss, not a pass.

    - ``incorrect``: an explicit ``"Incorrect"`` / ``"try again"`` (case-insensitive).
    - ``correct``: a positive signal — ``"Correct"`` or ``"Well done"`` (case
      sensitive, so the lowercase "correct" inside "Incorrect" is *not* one), or any
      of ``good`` / ``passed`` / ``success`` / ``accepted`` / ``great`` — that is
      *not* contradicted by an ``incorrect`` signal.
    - ``complete``: the quiz has finished (``is_quiz_complete``'s default markers).

    This replaces an inline check in ``run_quizzes_v2``'s text-response path whose
    positive test ran *before* the negative one, so a loose ``"good"`` in the
    grader's prose could mask an ``"Incorrect"`` and bank a wrong answer as right.
    On the strings the grader actually emits it agrees with that old inline check;
    it diverges only by no longer misreading a positive-word-plus-``Incorrect``
    page as a pass (the bug it fixes).
    """
    lowered = text.lower()
    incorrect = "incorrect" in lowered or "try again" in lowered
    positive = (
        "Correct" in text
        or "Well done" in text
        or any(word in lowered for word in ("good", "passed", "success", "accepted", "great"))
    )
    return AnswerResult(
        correct=positive and not incorrect,
        incorrect=incorrect,
        complete=is_quiz_complete(text),
    )
