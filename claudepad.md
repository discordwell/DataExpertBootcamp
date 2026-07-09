# Claudepad — Session Memory

## Session Summaries (most recent first; keep 20)

### 2026-07-09T00:00Z — Maintenance pass: extract+test the cross-quiz run tally; drop the flagged dead code
Continued the "pure logic lives in one tested place / single source of truth"
trajectory and cleared the item the last pass explicitly left for later. Suite
grew 285 → 292 green, still browser-free. Code review (2 independent finder
angles) returned no findings; printed output is byte-identical.

- **`quiz_status.tally_quiz_results(results)` (new)** — the **cross-quiz**
  sibling of `summarize_quiz`. Rolls a list of per-quiz result dicts up into a
  `ResultTally(passed, total_questions, total_correct, pct)`. The `sum(...)`
  roll-up + divide-by-zero-safe `(correct/questions*100) if questions else 0`
  percentage was **duplicated** in `run_quizzes_v2`'s final summary and
  `run_all_quizzes`'s per-week summary (and its final summary); all three now
  call the helper. Uses `.get()` defaults, so a bare error placeholder
  (`{"slug","title","error"}`, which v2 records when a quiz raises) counts as
  zero instead of `KeyError` — generalizing v2's existing `.get()` handling to
  run_all too. New `TestTallyQuizResults` (7 cases incl. empty run, error
  placeholder, completed-but-zero-questions, and a differential check vs. the
  exact inline block both runners used).
- **Dead code cleared (the last pass's "left for later" note).** v2's
  free-form **text-response** path had a dead `feedback`/retry branch: the text
  grader is one-shot (a Check Answer sets `submitted=True`, which breaks the
  attempt loop), so the `feedback` recomputed in the `elif verdict.incorrect`
  branch was never re-read — the loop only re-attempts on a *failed CLI call*
  (`response is None`), before any grader feedback exists. Removed the
  recomputation and the now-vestigial `feedback` variable/plumbing in that
  branch (the SQL path's separate, genuinely-iterative `feedback` is untouched;
  `solve_text_response_with_claude`'s `feedback=None` param stays for the API).
- **Unused imports removed:** `import re` from **both** `run_quizzes_v2.py`
  (its only use was the deleted regex) and `run_all_quizzes.py` (already dead —
  the `Question N of M` regex there lives inside a JS string, not Python).
- Docs updated (README testing line + ARCHITECTURE quiz_status + testing
  sections).

### 2026-07-08T00:00Z — Maintenance pass: fix the text-answer scoring bug, extract+test summarize_quiz
First landed the prior pass's WIP (the two v2 bug fixes + `parse_mc_question` +
CI) as commit `a3ac476`, then fixed a fresh bug and centralized the last
duplicated decision. Suite grew 275 → 285 green, still browser-free.

- **Bug fixed — correct free-form text answers were never scored.** In
  `run_quizzes_v2.solve_quiz`, the SQL and MC paths do `result["score"] += 1`
  on a correct answer, but the **text-response** path only set `solved = True`
  and appended the question with `correct: True` — it never bumped `score`.
  Because the text question still counts in `total = len(questions)`, a
  correctly-answered text question **dragged the percentage down** (numerator
  short, denominator full), understating both the printed `pct` and the
  `pct >= 70` pass gate — so a text-heavy quiz answered perfectly could read as
  not-PASSED, and `main()`'s grand total was undercounted too. One-line fix:
  count it like the other two paths. (Root note: the three paths record
  correctness inconsistently — SQL `solved`, text `correct`, MC nothing — so the
  parallel `score` counter, not the questions list, is the real source of truth;
  deriving score from the list would need all three unified first, a riskier
  browser-code change, so the surgical increment was the safe fix.)
- **`quiz_status.summarize_quiz(score, num_questions)` (new):** the end-of-quiz
  tally was a **verbatim-duplicated** block in both runners —
  `pct = score/total*100`, `status = "PASSED" if pct >= 70 else f"{pct:.0f}%"`,
  `if pct >= 70: completed = True`. Now a pure `QuizSummary(pct, status, passed)`
  with a named `PASS_THRESHOLD_PCT = 70`; both runners call it, printed output
  byte-identical. Divide-by-zero-safe for the empty case. New
  `TestSummarizeQuiz` (10 cases incl. the 70% boundary and a differential check
  against the exact inline `>= 70` / `f"{pct:.0f}%"` logic it replaces).
- Docs updated (README testing line + ARCHITECTURE quiz_status + testing
  sections). Known-minor, left for a later pass: v2's text path has a dead
  `feedback`/retry branch (the grader is one-shot, so the recomputed feedback is
  never re-submitted) — harmless dead code, not touched to keep this change focused.

### 2026-07-02T21:00Z — Maintenance pass: two v2-runner bug fixes, quiz_solver's parser extracted, CI added
Suite grew 248 → 275 green, still browser-free — and now enforced by CI.

- **Bug fixed — failed text-response CLI calls were *submitted as answers*.**
  `solve_text_response_with_claude` returned truthy sentinels on failure
  ("Unable to generate response", "… - timeout") and even fell back to
  **stderr** when stdout was empty — all of which the runner typed into the
  textarea and submitted, spending the question's one graded attempt on
  boilerplate (or a CLI error message). It also never checked the exit code.
  New pure `quiz_parsing.text_response_from_cli(returncode, stdout)` → cleaned
  answer or `None`; the caller already retries on `None` (and after the last
  attempt moves on without submitting). Contract now mirrors the SQL path.
  New `TestTextResponseFromCli` (7 cases incl. a "never a sentinel" guard).
- **Bug fixed — next-question wait compared against the loop counter.** The v2
  wait used `new_progress.current > q_num + 1`; `q_num` is the 0-based loop
  iteration, which drifts from the on-screen number after any stuck-wait or
  SQL/text iteration, so the wait spun its full 5 s after the next question had
  loaded (or broke early on a mid-quiz resume). New pure
  `quiz_status.question_advanced(answered, seen)` compares the two parsed
  positions; the runner passes the `progress` it parsed before answering.
  New `TestQuestionAdvanced` (6 cases incl. the off-by-one scenario itself).
- **`quiz_status.parse_mc_question(text)` (new):** extracted quiz_solver's last
  inline page-text parser (question after "% Complete", options between the
  choice badge and "Show Hint"). The inline copy had drifted from the proven
  runners: it took the line *immediately* after "% Complete" — on the real
  modal layout, the "Single Choice" badge itself — as the question, then
  offered the actual question as a clickable option. The helper adopts the
  primary runner's selection rule (skip badge lines, first line > 10 chars in
  the next 4) and excludes the question from the options.
  New `TestParseMCQuestion` (13 cases, both modal layouts).
- **CI (new):** `.github/workflows/tests.yml` — pytest on push/PR (python 3.12,
  ubuntu) plus `compileall` so syntax errors in the browser-bound scripts the
  tests don't import still fail the build. browser-cookie3 pulls pure-Python
  jeepney on py≥3.7 Linux, so no native build risk.
- Dead-code: removed v2's never-read `answer_idx`. Docs updated (README
  testing section + ARCHITECTURE quiz_status/quiz_parsing/testing sections).

### 2026-06-24T12:00Z — Maintenance pass: extract+test the "Question N of M" reader; fix dead scraper helper
Continued the "pure logic lives in one tested place / single source of truth"
trajectory and cleaned up two smaller defects. Suite grew 229 → 248 green, still
browser-free.

- **`quiz_status.parse_question_progress(text)` (new):** the last duplicated
  page-text regex. `re.search(r'Question (\d+) of (\d+)', text)` was inlined at
  **four** Python call sites — `run_quizzes_v2` (×3: question-present check,
  stuck-detection, next-question wait) and `quiz_solver` (×1). Now a pure helper
  returning a `QuestionProgress(current, total)` named tuple (or `None`).
  Differential-tested against the exact inline regex; rewired all four sites. The
  v2 stuck-detection site now **reuses** the `progress` already parsed from the
  same `full_text` instead of re-running the regex (one fewer search; verified
  `full_text` is unchanged and `progress` is non-None past the earlier break).
  Also dropped `quiz_solver`'s now-unused `import re`.
- **Bug fix — `scraper.extract_challenge_links` was dead + non-deterministic.**
  The README advertises scraper.py's "challenge-link extraction", but the helper
  was **never called** and returned `list(set(...))` (non-deterministic order).
  Now order-preserving de-dup, wired into `test_auth` so the advertised feature
  actually runs and prints the found links. New `tests/test_scraper.py` (7 cases:
  pattern match, root-relative-only, case-insensitive keyword, stable dedup order).
- **Dead-import cleanup:** removed unused `import re` from `scrape_lessons.py`,
  `scrape_quiz.py`, `browser_scraper.py` (none referenced `re`).
- New `tests/test_quiz_status.py::TestParseQuestionProgress` (12 cases incl. the
  legacy-regex differential). Reviewed the diff with a sub-agent: no regressions.

### 2026-06-24T00:00Z — Maintenance pass: extract+test the free-form text-response verdict
Closed out the "every grader-verdict check lives in one tested place" goal. The
prior pass unified the MC and SQL verdict checks onto
`quiz_status.interpret_answer_result`, but the v2 runner's **free-form
text-response** path still read the verdict with its own inline, untested string
matching — and that copy had a real **precedence bug**. Suite grew 215 → 229
green, still browser-free.

- **`quiz_status.interpret_text_result(text)` (new):** the text-response
  counterpart to `interpret_answer_result`. The fuzzier design/interview grader
  uses a wider positive vocabulary (`Well done` / `passed` / `accepted` / `great`
  / a bare `good`); an explicit `Incorrect` / `try again` now **vetoes** those
  looser positives. Returns the same `AnswerResult(correct, incorrect, complete)`.
- **Bug fixed — loose positive masked an explicit miss.** The old inline branch
  tested the positives (incl. a bare `good`) *before* the negative, so grader
  feedback like "a good attempt, but **incorrect**" was banked as a **pass**
  (`solved=True`, the wrong answer recorded correct). Negative now wins.
- **Verified safe before rewiring.** A differential check against the exact
  pre-fix inline logic over the realistic grader strings is identical on every
  one; it diverges *only* on the positive-word-plus-`Incorrect` pages it was
  getting wrong. New `tests/test_quiz_status.py::TestInterpretTextResult` (14 cases).
- Rewired v2's text path to the helper; `re`-based feedback extraction kept inline
  (it only annotates the recorded failure — the grader is one-shot).

### 2026-06-23T22:00Z — Maintenance pass: unify the grader-verdict reader across all 3 runners
Continued the "pure logic lives in tested modules / single source of truth"
trajectory — the answer-correctness check after each "Check Answer" was the last
duplicated, drifting, untested page-text interpreter. Suite grew 202 → 215 green,
still browser-free.

- **`quiz_status.interpret_answer_result(text)` (new):** returns an
  `AnswerResult(correct, incorrect, complete)`. `correct` = explicit `Correct!`
  or an `Output matches` SQL pass not contradicted by `does not match`;
  `incorrect` = `Incorrect` / `does not match`; `complete` reuses `is_quiz_complete`.
- **Killed 4 divergent inline copies.** The verdict check was inlined and had
  **drifted**: `run_quizzes_v2`'s SQL site (`solve_quiz`) lacked its own MC site's
  `does not match` guard, and `run_all_quizzes` / `quiz_solver` keyed off a looser
  bare `Correct` rather than the primary (49/49) runner's proven `Correct!`. All
  four now call the one helper.
- **Verified safe before rewiring.** Exhaustive differential check over the
  powerset of every marker fragment: identical to the v2 MC site on all three
  fields; identical to the v2 SQL/`run_all`/`quiz_solver` sites on every string
  the live grader actually emits (`Correct!` on a pass, `Incorrect` on a miss).
  Diverges only on contrived inputs (a bare un-banged `Correct`, or both
  `Output matches` and `does not match` at once) — where the new behavior is
  strictly more correct. New `tests/test_quiz_status.py::TestInterpretAnswerResult`
  (13 cases).
- Also deduped `solve_quiz`'s SQL completion check (an inline JS copy of
  `is_quiz_complete`'s markers + `Lesson Completed`) onto the shared helper.

### 2026-06-18T00:00Z — Maintenance pass: extract+test the Claude prompt builders
Continued the "pure logic lives in tested modules / single source of truth"
trajectory — the last untested pure logic in the v2 runner was the *prompt
construction* (the parsing half already lived in `quiz_parsing`). Suite grew
166 → 200 green, still browser-free.

- **`quiz_prompts.py` (new):** extracted the three Claude-prompt builders that were
  inlined inside `run_quizzes_v2`'s `solve_*_with_claude` functions next to the
  `subprocess.run` call — `build_mc_prompt` (option lettering + research-context
  injection + single/multi-select wording), `build_sql_prompt` (Trino prompt +
  `{"name","type"}` column normalization + optional sample-data/feedback sections),
  and `build_text_prompt` (design answers + optional feedback), plus helpers
  `option_letters` / `format_options` / `valid_letters_phrase` / `normalize_sql_columns`.
  Verified **byte-for-byte identical** to the original inline f-strings over **90k
  randomized inputs** (for the realistic ≤4-option range) before rewiring the runner.
  New `tests/test_quiz_prompts.py` (32 cases).
- **Latent bug fixed — the 5+-option cap.** Option letters were hard-coded to `A`-`D`
  in both the prompt (`valid_letters`/`chr(65+i)`) and the parser
  (`quiz_parsing.parse_mc_answer`'s `"ABCD"[:n]`), so a question with five or more
  options could never have its later options offered to — or recognized from — the
  model. Both now use the full alphabet; phrasing/parsing for ≤4 options is unchanged.
  Added 2 `test_quiz_parsing` regression cases (selecting `E`, multi-select past `D`).
- Rewired the three `solve_*_with_claude` functions to call the builders; net ~−140
  lines of inline prompt strings removed from the runner. No behavior change for the
  bootcamp's actual (≤4-option) quizzes.

### 2026-06-17T23:30Z — Maintenance pass: extract+test the page-text/score interpreters
Continued the "pure logic lives in tested modules / single source of truth"
trajectory. Suite grew 134 → 166 green, still browser-free.

- **`quiz_status.py` (new):** extracted the page-`innerText` interpreters that were
  inlined in `run_quizzes_v2.py`. The `X/Y (Z%)` score regex was **duplicated three
  times** (the two already-completed checks in `solve_quiz` + `check_quiz_status`),
  and the quiz-completion string check was scattered across both runners. New pure
  helpers: `parse_score` (→ `Score` named tuple; the trailing `(N%)` is required so a
  date like `26/12/2025` isn't read as a score), `is_perfect_completion` (the
  "already perfect, skip" rule), `classify_status` (perfect/incomplete/completed/
  not_started/unknown for the status report), and `is_quiz_complete(text,
  check_progress=…)`. Verified the new helpers make **identical decisions** to the
  original inline logic across **200k randomized inputs** over all five call sites
  before rewiring. New `tests/test_quiz_status.py` (32 cases).
- Rewired `run_quizzes_v2.py` (3 score sites + 3 completion checks) and
  `quiz_solver.py` (1 completion check) to the shared helpers. Net −17 lines in the
  two runners; the score regex no longer appears anywhere in the runners.
- Messages preserved verbatim (sites print `5/5 = 100%` vs the status report's
  `5/5 (100%)` — both kept exactly).

### 2026-06-17T13:17Z — Maintenance pass: centralize curriculum, extract+test response parsers
Continued the "pure logic lives in tested modules / single source of truth" trajectory.
Suite grew 92 → 134 green, still browser-free.

- **`quiz_parsing.py` (new):** extracted the three pure Claude-response parsers out of
  `run_quizzes_v2.py` — `parse_mc_answer` (MC letter extraction + multi-select dedup),
  `extract_sql` (markdown-fence stripping + single-line normalize + validate), and
  `clean_text_response` (preamble strip). Verified **byte-for-byte identical** to the
  original inline logic over 100k randomized inputs before swapping the runner to call
  them. `parse_mc_answer` is also now safe for `num_options == 0` (old code raised on the
  empty regex char class). New `tests/test_quiz_parsing.py` (29 cases).
- **`quizzes.py` (new):** centralized the quiz curriculum (`CURRICULUM` by week +
  derived flat `ALL_QUIZZES`). It was duplicated in both runners and had **drifted**:
  `run_quizzes_v2` was missing the Week 3 "Big O Notation" quiz (49 vs the 50 in
  `run_all_quizzes`), and v2's `status_check` re-derived weeks with brittle magic-number
  slices (`ALL_QUIZZES[0:5]`, …). Both runners now import the shared list; v2's
  `status_check` iterates `CURRICULUM` directly. Confirmed the shared `CURRICULUM` is
  identical to run_all's old copy (that runner unchanged) and v2 gains exactly the one
  missing slug. New `tests/test_quizzes.py` (7 invariants).
- v2 log titles are now the descriptive ones (e.g. "Python Tuesday" vs "Tuesday Quiz") —
  cosmetic; titles are display-only, nothing keys off them. Net −204/+19 lines in the
  two runners (logic moved into the shared modules).

### 2026-06-17T09:02Z — Maintenance pass: finish centralization, kill dead code, fix two bugs
Continued the prior refactor. First committed the staged WIP (shared modules + tests +
docs) as `cbf922d`, then improved on it.

- **Finished the "single source of truth" goal.** Added `CDP_PORT`/`CDP_URL` and a pure
  `lesson_url(slug)` to `common.py`, then wired *every* remaining script to it — the four
  files the prior pass skipped (`browser_scraper.py`, `debug_quizzes.py`, `inspect_quiz.py`,
  `inspect_sql_quiz.py`) plus the three runners. No more hardcoded `http://localhost:9222`
  or `{BASE_URL}/lesson/{slug}` anywhere. Dropped now-unused imports (`pathlib.Path`,
  `os`, `subprocess` in `quiz_solver`).
- **Bug fix — primary runner only ran one quiz.** `run_quizzes_v2.main()` iterated the
  stale one-element `RETRY_QUIZZES`, contradicting the README ("solves all quizzes"). Now
  iterates `ALL_QUIZZES` (49); `solve_quiz` already skips perfect quizzes so it's
  idempotent. Progress file renamed `retry_progress.json` → `v2_progress.json`.
- **Dead code removed** from `run_quizzes_v2.py`: `REMAINING_WEEKS`, `NEEDS_100_PERCENT`,
  `CODE_QUESTIONS_QUIZZES`, `RETRY_QUIZZES` (all defined, never used).
- **Bug fix + extraction — `generate_sql`.** Moved it to a new pure module `quiz_sql.py`
  (mirrors `quiz_heuristics`). Fixed a `TypeError`: it `", ".join(...)`-ed the
  `{"name","type"}` column dicts the DOM parser yields, crashing the SQL fallback path.
  Now normalizes dicts→names. Verified byte-for-byte identical to the original across all
  15 template branches for string-form columns.
- **Tests:** new `tests/test_quiz_sql.py` (9 cases incl. the dict regression) + new
  `test_common` cases for `lesson_url`/`CDP_URL`. Suite is 92 green, still browser-free.

### 2026-06-10T21:41Z — Maintenance pass: shared modules, tests, docs
Refactored the repo from a flat pile of scripts into something with shared
infrastructure, tests, and documentation. No behavior changes to the live quiz/scrape
flows (which can't be exercised offline).

- **`quiz_heuristics.py` (new):** extracted the canonical ~100-rule `get_answer` keyword
  heuristic out of `run_all_quizzes.py`. Verified byte-for-byte behavior identity against
  the git-HEAD original across 3,888 differential checks. Refactored `run_all_quizzes.py`
  and `quiz_solver.py` to import it. Removed the **dead** (never-called) `get_answer` from
  `run_quizzes_v2.py` (that runner answers via the Claude CLI).
- **`common.py` (new):** single source of truth for `BASE_URL`, `DATA_DIR`,
  `get_cookies_for_playwright` (was duplicated verbatim in `scrape_quiz.py` +
  `scrape_lessons.py`), and `get_session` (from `scraper.py`). Refactored all three
  scrapers to use it.
- **Tests (new):** `tests/test_quiz_heuristics.py` + `tests/test_common.py`, 81 tests,
  all green. Browser-free — `browser_cookie3` is monkeypatched. Added `pytest.ini`
  (`pythonpath = .`).
- **Docs (new):** `README.md`, `ARCHITECTURE.md`, `requirements.txt`,
  `requirements-dev.txt`.

## Key Findings (persistent)

- **Two answering strategies:** `run_quizzes_v2.py` is the primary runner and uses the
  `claude` CLI via `subprocess` for MC/SQL/free-text (iterates on grader feedback). The
  offline keyword heuristic (`quiz_heuristics.get_answer`) is the fallback used by
  `run_all_quizzes.py` and the older `quiz_solver.py`. When the CLI can't produce usable
  SQL, v2 falls back to the offline template generator `quiz_sql.generate_sql`.
- **Pure logic lives in tested modules:** `common.py` (config + auth helpers, incl.
  `CDP_URL`/`lesson_url`), `quizzes.py` (the canonical curriculum — `CURRICULUM` +
  `ALL_QUIZZES`), `quiz_heuristics.py`, `quiz_sql.py`, `quiz_prompts.py` (Claude
  MC/SQL/text prompt *builders*), `quiz_parsing.py` (Claude MC/SQL/text response
  *parsers*), and `quiz_status.py` (page-text interpreters —
  `parse_score`/`parse_question_progress`/`is_perfect_completion`/
  `classify_status`/`is_quiz_complete`/`interpret_answer_result` for MC+SQL /
  `interpret_text_result` for free-form text) are all browser-free and
  unit-tested. `run_quizzes_v2`'s `solve_*_with_claude` functions are
  now thin: build prompt (`quiz_prompts`) → call CLI → parse (`quiz_parsing`). Every
  script imports config from `common` and the quiz list from `quizzes`.
- **Auth model:** scripts reuse the user's logged-in Chrome session — cookies via
  `browser_cookie3`, and/or CDP attach to Chrome started with
  `--remote-debugging-port=9222`. No credentials are stored.
- **Brittle surface:** the quiz DOM selectors (`#modal-root .space-y-3`, the
  Quiz/Start-Quiz/Check-Answer buttons) track a live third-party site and are the most
  fragile part. The `inspect_*.py` scripts exist to re-derive them when the site changes.
- **Can't be CI-tested:** every runtime path needs a live browser, an authenticated
  dataexpert.io session, and (for v2) the `claude` CLI. Tests therefore cover only the
  pure logic.
- **Output:** everything goes to `data/` (git-ignored): HTML, screenshots, and rolling
  `quiz_progress.json` / `all_quiz_results.json`.
