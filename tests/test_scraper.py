"""Tests for the pure ``extract_challenge_links`` helper in ``scraper.py``.

``test_auth`` itself hits the live site (needs real cookies), but the link
extraction is pure string/regex work and is covered here with no network. The
helper was previously dead code (defined, never called) that returned
``list(set(...))`` — a non-deterministic order; these tests pin the
order-preserving de-duplication it now uses.
"""
from scraper import extract_challenge_links


def test_extracts_quiz_challenge_and_lesson_paths():
    html = (
        '<a href="/lesson/cumulative-data-quiz">Q1</a>'
        '<a href="/program/challenge/week-1">C</a>'
        '<a href="/lesson/intro">L</a>'
    )
    assert extract_challenge_links(html) == [
        "/lesson/cumulative-data-quiz",
        "/program/challenge/week-1",
        "/lesson/intro",
    ]


def test_ignores_non_challenge_links():
    html = '<a href="/about">About</a><a href="/lesson/x">X</a><a href="/pricing">P</a>'
    assert extract_challenge_links(html) == ["/lesson/x"]


def test_only_matches_root_relative_paths():
    # The pattern requires the captured href to begin with "/", so absolute URLs
    # are not captured (the live page links to root-relative paths).
    html = '<a href="https://www.dataexpert.io/lesson/x">abs</a><a href="/quiz/y">rel</a>'
    assert extract_challenge_links(html) == ["/quiz/y"]


def test_deduplicates_preserving_first_seen_order():
    html = (
        '<a href="/lesson/a">a</a>'
        '<a href="/quiz/b">b</a>'
        '<a href="/lesson/a">a again</a>'
        '<a href="/challenge/c">c</a>'
        '<a href="/quiz/b">b again</a>'
    )
    assert extract_challenge_links(html) == ["/lesson/a", "/quiz/b", "/challenge/c"]


def test_case_insensitive_keyword_match():
    html = '<a href="/LESSON/x">x</a><a href="/Quiz/y">y</a>'
    # Matching is case-insensitive; the captured path keeps its original case.
    assert extract_challenge_links(html) == ["/LESSON/x", "/Quiz/y"]


def test_empty_and_no_matches_return_empty_list():
    assert extract_challenge_links("") == []
    assert extract_challenge_links("<a href='/about'>no quotes match</a>") == []


def test_result_is_a_list():
    # Regression: it used to return list(set(...)) (non-deterministic order). The
    # return type is a list and repeated calls are stable.
    html = '<a href="/lesson/a">a</a><a href="/quiz/b">b</a>'
    first = extract_challenge_links(html)
    assert isinstance(first, list)
    assert first == extract_challenge_links(html)
