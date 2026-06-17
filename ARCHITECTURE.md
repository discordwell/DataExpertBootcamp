# Architecture

This repo is a set of small, single-purpose Python scripts that automate the
DataExpert.io bootcamp. They share two concerns — **authentication** and **answering
questions** — which are factored into shared modules so the individual scripts stay
thin.

## High-level flow

```
                ┌─────────────────────────────────────────────┐
                │            your logged-in Chrome             │
                │  (normal profile cookies  +  CDP :9222 tab)  │
                └───────────────┬───────────────┬─────────────┘
            cookies (browser_cookie3)      CDP (Playwright connect_over_cdp)
                                │               │
                    ┌───────────▼──────┐  ┌─────▼────────────────────────────┐
                    │  common.py       │  │  runners / scrapers              │
                    │  - BASE_URL      │  │  - run_quizzes_v2.py (Claude CLI)│
                    │  - DATA_DIR      │  │  - run_all_quizzes.py (heuristic)│
                    │  - get_session   │  │  - quiz_solver.py (heuristic)    │
                    │  - get_cookies_  │  │  - scrape_lessons.py / scrape_   │
                    │    for_playwright│  │    quiz.py / scraper.py          │
                    └───────────┬──────┘  └─────┬───────────────┬────────────┘
                                │               │               │
                                │     ┌─────────▼─────┐   ┌──────▼──────────┐
                                │     │quiz_heuristics│   │  claude CLI     │
                                │     │ .get_answer   │   │  (subprocess)   │
                                │     └───────────────┘   └─────────────────┘
                                ▼
                        data/  (HTML, screenshots, *.json progress)
```

## Shared modules

### `common.py`
Single source of truth for cross-cutting configuration and authentication:

- `BASE_URL`, `DATA_DIR` — the site root and the git-ignored output directory
  (created on import).
- `get_cookies_for_playwright(domain)` — reads Chrome cookies via `browser_cookie3`
  and converts them to the dict shape Playwright's `add_cookies` expects (with sane
  domain/path fallbacks and session-cookie handling).
- `get_session(domain)` — a `requests.Session` pre-loaded with those cookies and a
  desktop-Chrome User-Agent, for plain HTTP scraping.

Before this module existed, `get_cookies_for_playwright` was copy-pasted into two
scrapers and the constants were redefined in every file.

### `quiz_heuristics.py`
A pure, network-free function `get_answer(question, options) -> int` that picks an
option index using a long list of `topic → keyword` rules (one block per bootcamp
week), with a length-plus-jargon fallback scorer when nothing matches. Because it
touches nothing external, it is fully unit-tested in `tests/test_quiz_heuristics.py`.

This is the **offline** answering strategy. `run_quizzes_v2.py` prefers the Claude CLI
and does not use it; it remains the fallback engine for `run_all_quizzes.py` and
`quiz_solver.py`.

## The scripts

| Layer | Files | Notes |
| --- | --- | --- |
| **Runners** | `run_quizzes_v2.py`, `run_all_quizzes.py`, `quiz_solver.py` | Attach to Chrome over CDP, navigate each lesson's Quiz tab, parse questions from the rendered DOM, answer, and record progress to `data/`. v2 is the most advanced (Claude-backed, multi-question-type, resume-aware). |
| **Scrapers** | `scrape_lessons.py`, `scrape_quiz.py`, `scraper.py`, `browser_scraper.py` | Pull curriculum/lesson/quiz content. Most use Playwright + cookie injection; `scraper.py` uses `requests`; `browser_scraper.py` uses `nodriver`. |
| **Inspection** | `inspect_quiz.py`, `inspect_sql_quiz.py`, `debug_quizzes.py` | Throwaway helpers used to reverse-engineer the quiz DOM/selectors. Kept for reference. |

## Answering strategies

1. **Offline heuristic** (`quiz_heuristics.get_answer`)
   - Pros: instant, free, deterministic, testable.
   - Cons: keyword-matching only; weak on code-tracing or SQL-writing questions.

2. **Claude CLI** (`run_quizzes_v2.py`)
   - `solve_mc_with_claude` — multiple-choice (single/multi-select) with chain-of-thought
     prompting and an optional research-context file (`data/quiz_research.md`).
   - `solve_sql_with_claude` — writes SQL, then iterates using the grader's feedback.
   - `solve_text_response_with_claude` — free-form design answers.
   - Invoked via `subprocess.run(["claude", "-p", prompt])`.

## DOM interaction model

The quiz UI is a JS-rendered modal. The runners:
1. Click the **Quiz** tab, then **Start Quiz** (often twice — there's a confirmation modal).
2. Read `Question N of M`, the question text, and the option buttons from
   `#modal-root .space-y-3`.
3. Click the chosen option, click **Check Answer**, record correctness, then **Next**.
4. Detect completion (`Quiz Complete` / `You passed`) and a stuck-state guard to avoid
   infinite loops.

Because the selectors track a live third-party site, they are the most brittle part of
the codebase; the `inspect_*` scripts exist to re-derive them when the site changes.

## Output & state

Everything lands in `data/` (git-ignored): rendered HTML, debug screenshots, per-quiz
result JSON, and a rolling `quiz_progress.json` / `all_quiz_results.json` written after
each quiz so a run can be inspected or resumed.

## Testing strategy

Browser/network/CLI interactions can't be exercised in CI, so the tests target the pure
logic:
- `tests/test_quiz_heuristics.py` — locks in the heuristic's selections and edge cases.
- `tests/test_common.py` — verifies cookie conversion and session setup by monkeypatching
  `browser_cookie3` (no real browser or cookies needed).
