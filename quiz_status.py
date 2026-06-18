"""Pure helpers for interpreting a DataExpert quiz/lesson page's text.

The runners read ``document.body.innerText`` and then have to decide three things
from it: what score the page reports, whether a quiz is already perfect (so it can
be skipped on a re-run), and — for the status report — how to classify the lesson.

That decision logic is pure regex/string work with a genuine edge case: the score
pattern must match a quiz score like ``5/5 (100%)`` but *not* a calendar date such
as ``26/12/2025``. It used to be inlined and **duplicated three times** inside
``run_quizzes_v2``'s browser coroutines (the score regex appeared at three call
sites), where it could not be unit-tested.

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
