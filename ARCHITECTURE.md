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
- `CDP_PORT` / `CDP_URL` — the Chrome DevTools Protocol endpoint
  (`http://localhost:9222`) the CDP-based runners attach to.
- `lesson_url(slug)` — builds `{BASE_URL}/lesson/{slug}`, the URL every runner
  and scraper navigates to.
- `get_cookies_for_playwright(domain)` — reads Chrome cookies via `browser_cookie3`
  and converts them to the dict shape Playwright's `add_cookies` expects (with sane
  domain/path fallbacks and session-cookie handling).
- `get_session(domain)` — a `requests.Session` pre-loaded with those cookies and a
  desktop-Chrome User-Agent, for plain HTTP scraping.

Before this module existed, `get_cookies_for_playwright` was copy-pasted into two
scrapers, the CDP URL and lesson-URL pattern were re-typed in every runner, and
the constants were redefined in every file. All scripts — including the
`inspect_*`/`debug_quizzes` helpers — now import from here.

### `quizzes.py`
The canonical quiz curriculum — the single source of truth for the ~50
`(slug, title)` pairs. It exposes `CURRICULUM` (an ordered week → quizzes mapping)
and `ALL_QUIZZES` (the flat list, derived from `CURRICULUM`).

Both runners used to hardcode their own copy of this list and the copies drifted:
`run_quizzes_v2.py` was missing the Week 3 "Big O Notation" quiz (49 vs. 50), and
its `status_check` re-derived the week grouping with magic-number slices
(`ALL_QUIZZES[0:5]`, `[5:12]`, …) that break silently if the list is reordered.
Centralizing here keeps the runners in sync and lets the week grouping come from
real structure. Being pure data, it is verified by `tests/test_quizzes.py`.

### `quiz_heuristics.py`
A pure, network-free function `get_answer(question, options) -> int` that picks an
option index using a long list of `topic → keyword` rules (one block per bootcamp
week), with a length-plus-jargon fallback scorer when nothing matches. Because it
touches nothing external, it is fully unit-tested in `tests/test_quiz_heuristics.py`.

This is the **offline** answering strategy. `run_quizzes_v2.py` prefers the Claude CLI
and does not use it; it remains the fallback engine for `run_all_quizzes.py` and
`quiz_solver.py`.

### `quiz_sql.py`
A pure `generate_sql(question, tables, expected_cols) -> str` that maps keywords in a
SQL question to a Trino/Presto query template (running totals, ranking, sessionization,
"customers with no orders", etc.), filling in the expected output columns. It accepts
columns either as `{"name", "type"}` dicts (what the live DOM parser produces) or as
plain name strings.

`run_quizzes_v2.py` uses it only as the **offline fallback** when the Claude CLI fails
to return usable SQL. Extracting it from the runner (mirroring `quiz_heuristics`) keeps
it unit-testable in `tests/test_quiz_sql.py` without a browser or the CLI.

### `quiz_prompts.py`
Pure builders for the prompts `run_quizzes_v2.py` sends to the Claude CLI — the
counterpart to `quiz_parsing` (which parses the responses):

- `build_mc_prompt(question, options, research_context, multi_select)` — letters the
  options, injects the research context, and switches the answer-format / select
  instructions between single- and multi-select.
- `build_sql_prompt(question, table, expected_cols, feedback, sample_data)` — the
  Trino/Presto SQL prompt; normalizes the `{"name", "type"}` column dicts (or plain
  name strings) and includes the optional sample-data and previous-attempt-feedback
  sections.
- `build_text_prompt(question, feedback)` — the free-form design/interview prompt,
  with an optional feedback section.
- Helpers `option_letters`, `format_options`, `valid_letters_phrase`, and
  `normalize_sql_columns` carry the fiddly bits.

This construction used to be inlined inside the three `solve_*_with_claude` functions,
right next to the `subprocess.run` call, where it could not be tested. Pulling it out
(like `quiz_parsing`) makes the prompt text unit-testable in
`tests/test_quiz_prompts.py`, and the extraction was verified **byte-for-byte** against
the original inline f-strings over **90k randomized inputs** (for the realistic
≤4-option range) before the runner was rewired. The move also fixed a **latent bug**:
the option-letter logic capped at `A`-`D`, so a question with five or more options
could never have its later options offered to — or recognized from — the model;
`valid_letters_phrase` and `quiz_parsing.parse_mc_answer` now use the full alphabet.

### `quiz_parsing.py`
Pure parsers for the Claude CLI's raw responses, used by `run_quizzes_v2.py`:

- `parse_mc_answer(response, num_options, multi_select)` — pulls the chosen option
  index/indices out of the model's text (an `<answer>…</answer>` block first, then
  standalone capital letters), de-duplicating multi-select picks.
- `extract_sql(raw)` — strips markdown ```` ```sql ```` fences, grabs from the first
  SQL keyword, collapses to a single line, and validates it as SQL (or `None`).
- `clean_text_response(response)` — strips a leading "Here is" / "My answer:" /
  "Response:" preamble.

This logic used to live inside the subprocess-calling solver functions where it
could not be tested. Pulling it into a pure module (like `quiz_heuristics` and
`quiz_sql`) makes the fiddly LLM-output edge cases unit-testable in
`tests/test_quiz_parsing.py`. The extraction was verified byte-for-byte against the
original inline logic over 100k randomized inputs.

### `quiz_status.py`
Pure interpreters for a quiz/lesson page's `innerText`, used by `run_quizzes_v2.py`
(and `quiz_solver.py`):

- `parse_score(text)` — pulls the `X/Y (Z%)` score out of the page as a `Score`
  named tuple. The pattern **requires** the trailing `(N%)`, which is what stops
  it from mistaking a calendar date like `26/12/2025` for a `got/total` fraction.
- `is_perfect_completion(text)` — the canonical "this quiz is already perfect,
  skip it" rule: a 100%-and-all-correct score, or a bare `(100%)` marker when no
  fraction is present.
- `classify_status(text)` — for the no-retake status report; returns one of
  `perfect` / `incomplete` / `completed` / `not_started` / `unknown` plus a
  human-readable score.
- `is_quiz_complete(text, check_progress=…)` — whether an in-progress quiz has
  finished (`Quiz Complete` / `You passed`, optionally also a `100% Complete`
  progress bar).

The `X/Y (Z%)` score regex was **inlined three times** inside `run_quizzes_v2`'s
browser coroutines (the two already-completed checks in `solve_quiz` and the
status check), and the quiz-completion string check was scattered across both
runners. Centralizing the decisions here removes that duplication and — like the
other pure modules — makes the date-vs-score edge case unit-testable in
`tests/test_quiz_status.py`. The extraction was verified to make identical
decisions to the original inline logic over 200k randomized inputs before the
runners were rewired.

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
     Falls back to `quiz_sql.generate_sql` (template-based) when the CLI fails.
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
logic and stay browser-free (no Playwright import required to run them):
- `tests/test_quiz_heuristics.py` — locks in the heuristic's selections and edge cases.
- `tests/test_quiz_sql.py` — exercises each SQL template branch and guards the
  dict-shaped-columns regression (`generate_sql` used to crash joining column dicts).
- `tests/test_quiz_prompts.py` — pins the Claude-prompt builders: research-context
  injection, single/multi-select wording, SQL column normalization, the optional
  feedback/sample-data sections, and the 5+-option lettering fix.
- `tests/test_quiz_parsing.py` — pins the Claude-response parsers: MC letter
  extraction, multi-select de-duplication (including letters beyond D), markdown
  SQL-fence stripping, and preamble cleanup.
- `tests/test_quiz_status.py` — pins the page-text interpreters: score parsing
  (including the date-isn't-a-score regression), the perfect-completion skip
  rule, the status classifier's five outcomes, and quiz-completion detection.
- `tests/test_quizzes.py` — guards the curriculum invariants: eight weeks, fifty
  quizzes, unique slugs, and a flat `ALL_QUIZZES` that matches the week grouping.
- `tests/test_common.py` — verifies cookie conversion, session setup, and the
  `CDP_URL`/`lesson_url` helpers by monkeypatching `browser_cookie3` (no real browser
  or cookies needed).
