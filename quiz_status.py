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
from typing import List, NamedTuple, Optional, Tuple

# Matches a quiz score like "5/5 (100%)". The trailing "(N%)" is REQUIRED, which
# is what stops the pattern from matching a calendar date such as "26/12/2025"
# (a date has no percentage after it).
SCORE_RE = re.compile(r'(\d+)/(\d+)\s*\((\d+)%\)')

# Bare-percentage fallback, e.g. a "(100%)" with no "got/total" fraction.
PERCENT_RE = re.compile(r'\((\d+)%\)')

# Matches the "Question N of M" position label the quiz modal shows above each
# question. The runners use it both to tell that a question is on screen and to
# read the current/total counts (for stuck-detection and next-question waits).
QUESTION_RE = re.compile(r'Question (\d+) of (\d+)')


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


class QuestionProgress(NamedTuple):
    """The quiz modal's "Question N of M" position: question ``current`` of ``total``."""

    current: int
    total: int


def parse_question_progress(text: str) -> Optional[QuestionProgress]:
    """Extract the "Question N of M" position from quiz page text, or ``None``.

    Returns ``None`` when the marker is absent, which the runners treat as "no
    question is on screen" — the quiz either hasn't started yet or has finished.
    This regex used to be inlined at four call sites across the runners (three in
    ``run_quizzes_v2``, one in ``quiz_solver``); centralizing it here keeps the
    single ``Question N of M`` pattern in one tested place.
    """
    m = QUESTION_RE.search(text)
    if not m:
        return None
    return QuestionProgress(int(m.group(1)), int(m.group(2)))


def question_advanced(answered: QuestionProgress, seen: Optional[QuestionProgress]) -> bool:
    """Whether the page has moved past the question the runner just answered.

    ``answered`` is the position parsed *before* answering; ``seen`` is the
    position parsed after clicking Next (``None`` when no question is on screen,
    e.g. mid-transition — which is not an advance).

    The v2 runner's next-question wait used to compare the new position against
    its 0-based loop-iteration counter (``current > q_num + 1``). That counter
    drifts from the on-screen question number whenever an iteration is consumed
    by a stuck-wait or by a SQL/text question, so after any hiccup the wait
    either spun its full timeout after the next question had already loaded, or
    broke early on a quiz resumed mid-way. Comparing the two parsed positions is
    exact.
    """
    return seen is not None and seen.current > answered.current


# The choice-type badge the quiz modal shows between the progress bar and the
# question, and the navigation-control labels that also appear as bare lines in
# the modal's innerText. The text-based question/option parser must skip both.
CHOICE_LABELS = ("Single Choice", "Multiple Choice")
_NAV_LINES = frozenset({"Notes", "Quiz", "Previous", "Next", "Module"})


class MCQuestion(NamedTuple):
    """A multiple-choice question read from the quiz modal's text: the question
    line plus the option lines that follow it."""

    question: str
    options: List[str]


def parse_mc_question(text: str, *, max_options: int = 6) -> Optional[MCQuestion]:
    """Parse a multiple-choice question and its options out of quiz-modal text.

    The modal's ``innerText`` reads roughly ``Question N of M`` / ``NN%
    Complete`` / a ``Single Choice``/``Multiple Choice`` badge / the question /
    the option lines / ``Show Hint`` / ``Check Answer``. This picks:

    - ``question``: the first substantial line (> 10 chars) within the few lines
      after ``% Complete``, skipping any line carrying a choice-type badge — the
      same selection rule the primary runner's DOM parser uses.
    - ``options``: the lines after the badge up to ``Show Hint`` /
      ``Check Answer``, excluding the question line itself and the surrounding
      navigation labels, capped at ``max_options``.

    Returns ``None`` when no question or no options could be found (the caller
    treats that as a parse error).

    This logic was inlined — untested — in ``quiz_solver``, and that copy had
    drifted from the proven runners: it took the line *immediately* after
    ``% Complete`` as the question, so on the real modal layout it read the
    ``Single Choice`` badge as the question text and then offered the actual
    question as one of the clickable options.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    question = ""
    for i, line in enumerate(lines):
        if "% Complete" in line:
            for candidate in lines[i + 1:i + 5]:
                if any(label in candidate for label in CHOICE_LABELS):
                    continue
                if len(candidate) > 10:
                    question = candidate
                    break
            break

    options: List[str] = []
    in_options = False
    for line in lines:
        if any(label in line for label in CHOICE_LABELS):
            in_options = True
            continue
        if in_options:
            if "Show Hint" in line or "Check Answer" in line:
                break
            if line != question and line not in _NAV_LINES:
                options.append(line)
    options = options[:max_options]

    if not question or not options:
        return None
    return MCQuestion(question, options)


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


# A quiz counts as passed at 70% correct — the threshold both runners use both to
# mark a quiz "completed" and to label its one-line end-of-quiz summary.
PASS_THRESHOLD_PCT = 70


class QuizSummary(NamedTuple):
    """The end-of-quiz summary both runners print from the final tally: the
    percent correct, the short status label (``"PASSED"`` or e.g. ``"60%"``), and
    whether the pass threshold was met."""

    pct: float
    status: str
    passed: bool


def summarize_quiz(score: int, num_questions: int) -> QuizSummary:
    """Summarize a finished quiz run from its score and answered-question count.

    Returns the percent correct, the short status label the runners print
    (``"PASSED"`` at or above the 70% threshold, otherwise the rounded percentage
    like ``"60%"``), and whether the quiz passed. ``num_questions == 0`` yields
    0% and not-passed — the runners only summarize once at least one question was
    answered, but the helper stays safe for the empty case rather than dividing by
    zero.

    Both runners computed this inline with a verbatim-duplicated ``>= 70``
    threshold and ``f"{pct:.0f}%"`` label; centralizing it keeps the single pass
    rule in one tested place (like the rest of this module).
    """
    pct = (score / num_questions * 100) if num_questions else 0.0
    passed = pct >= PASS_THRESHOLD_PCT
    status = "PASSED" if passed else f"{pct:.0f}%"
    return QuizSummary(pct, status, passed)
