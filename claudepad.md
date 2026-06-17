# Claudepad — Session Memory

## Session Summaries (most recent first; keep 20)

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
  `run_all_quizzes.py` and the older `quiz_solver.py`.
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
