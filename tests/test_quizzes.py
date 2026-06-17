"""Tests for the canonical quiz curriculum in ``quizzes``.

The curriculum used to be copy-pasted into both runners and drifted (the v2 list
silently dropped the Week 3 "Big O Notation" quiz). These tests lock in the
structure so the single source of truth stays consistent: unique slugs, a flat
list that matches the week grouping, and the full 50-quiz set.
"""
from quizzes import ALL_QUIZZES, CURRICULUM


def test_eight_weeks():
    assert len(CURRICULUM) == 8
    assert list(CURRICULUM)[0] == "Week 1: Data Modeling"
    assert list(CURRICULUM)[-1] == "Week 8: AI Engineer Interview"


def test_total_is_fifty_quizzes():
    assert len(ALL_QUIZZES) == 50
    assert sum(len(v) for v in CURRICULUM.values()) == 50


def test_all_quizzes_is_flat_curriculum_in_order():
    flattened = [quiz for quizzes in CURRICULUM.values() for quiz in quizzes]
    assert ALL_QUIZZES == flattened


def test_slugs_are_unique():
    slugs = [slug for slug, _ in ALL_QUIZZES]
    assert len(slugs) == len(set(slugs))


def test_every_entry_is_a_slug_title_pair():
    for entry in ALL_QUIZZES:
        assert isinstance(entry, tuple) and len(entry) == 2
        slug, title = entry
        assert isinstance(slug, str) and slug.strip()
        assert isinstance(title, str) and title.strip()


def test_includes_previously_missing_big_o_quiz():
    # The v2 runner used to skip this one; the shared list must keep it.
    slugs = {slug for slug, _ in ALL_QUIZZES}
    assert "mondaybigonotation-24a31" in slugs


def test_week_three_has_seven_quizzes():
    assert len(CURRICULUM["Week 3: Python & Data Structures"]) == 7
