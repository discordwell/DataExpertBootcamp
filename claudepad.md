# Claudepad — Session Memory

## Session Summaries (most recent first; keep 20)

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
  `CDP_URL`/`lesson_url`), `quiz_heuristics.py`, and `quiz_sql.py` are all browser-free
  and unit-tested. Every script imports config from `common`.
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
