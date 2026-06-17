# data-expert-bootcamp

Personal automation toolkit for working through the [DataExpert.io](https://www.dataexpert.io)
data-engineering bootcamp. It drives a logged-in Chrome session to scrape lesson/quiz
content and to auto-answer the end-of-lesson quizzes (~50 quizzes across 8 weeks:
data modeling, SQL, Python & data structures, pipelines, ML/AI, distributed computing,
and the DE/AI interview tracks).

The scripts reuse **your own** authenticated browser session — you log into
dataexpert.io once in Chrome and the tools read those cookies. Nothing here stores
or transmits credentials.

## How it works

Two pieces make authentication painless:

1. **Cookie reuse** — `browser_cookie3` reads the dataexpert.io cookies straight out
   of your local Chrome profile, so the scripts inherit your logged-in session.
2. **CDP attach** — the quiz runners attach to a Chrome you started with remote
   debugging (`--remote-debugging-port=9222`) and operate the real, already-authenticated
   tab via Playwright. This avoids fragile re-login flows.

Quizzes are answered with one of two strategies:

- **Offline keyword heuristic** (`quiz_heuristics.get_answer`) — a fast, dependency-free
  best guess used by `run_all_quizzes.py` and `quiz_solver.py`.
- **Claude CLI** (`run_quizzes_v2.py`) — shells out to the `claude` CLI to answer
  multiple-choice, free-text, and SQL-writing questions, iterating on feedback. This is
  the most capable runner. When the CLI can't return usable SQL it falls back to the
  offline template generator in `quiz_sql.generate_sql`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full component map and data flow.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt       # + pytest, for running the tests

# Playwright needs a browser. Either install the bundled one:
playwright install chromium
# ...or rely on attaching to your own Chrome (see below).
```

For the CDP-based runners, start Chrome with remote debugging and log in:

```bash
# Close existing Chrome windows first, then:
open -a 'Google Chrome' --args --remote-debugging-port=9222
# Log into https://www.dataexpert.io in that window.
```

`run_quizzes_v2.py` additionally requires the [`claude` CLI](https://www.anthropic.com)
to be installed and authenticated.

## Usage

| Script | What it does |
| --- | --- |
| `python run_quizzes_v2.py` | **Primary runner.** Solves all quizzes using the Claude CLI (MC + SQL + free-text), skipping ones already at 100%. |
| `python run_quizzes_v2.py status` | Reports completion/score status for each quiz without retaking. |
| `python run_all_quizzes.py` | Solves the full curriculum using only the offline keyword heuristic (no Claude). |
| `python quiz_solver.py` | Early single-quiz solver (offline heuristic). Superseded by the runners above. |
| `python scrape_lessons.py` | Scrapes the lesson/curriculum list to `data/`. |
| `python scrape_quiz.py` | Scrapes one quiz's questions/options to `data/`. |
| `python scraper.py` | Quick `requests`-based auth check + challenge-link extraction. |
| `python browser_scraper.py` | Alternative curriculum scraper using `nodriver` (optional dep). |
| `python inspect_quiz.py` / `inspect_sql_quiz.py` / `debug_quizzes.py` | One-off DOM inspection helpers used while building the selectors. |

All scraped HTML, screenshots, and progress JSON are written to `data/`, which is
git-ignored.

## Testing

The pure logic (the answer heuristic, the SQL template generator, and the cookie/session
helpers) is covered by a browser-free pytest suite:

```bash
python -m pytest
```

The tests monkeypatch `browser_cookie3` so they run offline with no real cookies, lock in
the heuristic's option-selection behavior, and exercise every `quiz_sql` template branch
(including the dict-shaped-columns regression).

## Responsible use

This is a personal learning aid for the author's own bootcamp enrollment. It only ever
acts as the logged-in user, against the author's own account. Don't point it at accounts
or services you aren't authorized to use, and respect DataExpert.io's terms of service.

## Repository layout

```
common.py            Shared config (BASE_URL, DATA_DIR, CDP_URL, lesson_url) + auth helpers
quiz_heuristics.py   Offline keyword heuristic for multiple-choice answers (pure, tested)
quiz_sql.py          Offline template-based SQL generator / fallback (pure, tested)
run_quizzes_v2.py    Primary runner — answers via the Claude CLI
run_all_quizzes.py   Full-curriculum runner — answers via the offline heuristic
quiz_solver.py       Early single-quiz solver (heuristic)
scrape_lessons.py    Curriculum/lesson scraper (Playwright)
scrape_quiz.py       Single-quiz scraper (Playwright)
scraper.py           requests-based auth check
browser_scraper.py   nodriver-based curriculum scraper (optional)
inspect_*.py         DOM inspection one-offs
tests/               Browser-free pytest suite
data/                Scraped output + progress (git-ignored)
```
